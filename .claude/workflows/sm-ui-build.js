// sm-ui-build -- UI build workflow (directive #2). Rosetta-Stone of /report-fixes' parallel-build half,
// recast for greenfield UI: judge-panel CONCEPT -> file-disjoint direct BUILD -> adversarial multi-lens
// REVIEW + bounded repair -> main-thread build/axe GATE handoff.
// Build units are file-DISJOINT (union-find), so parallel agents write distinct files under targetDir
// directly (NOT worktree-isolated) -- distinct-file concurrent writes cannot collide and the generated
// spike files persist in the main working tree (worktree isolation would discard them on cleanup).
//
// PERSONA: every builder/reviewer adopts docs/KingModePrompt.txt (Senior Frontend Architect; anti-generic,
// bespoke, asymmetry, intentional minimalism, WCAG AAA) -- but BOUND by the MUST constraints from
// UI-DESIGN-SPEC.md so awe-inspiring craft cannot violate INTENT/firewall/ADR-18.
//
// SCOPE (operator-locked 2026-06-10): EXPERIMENTAL spike. Writes to a SEPARATE prototype path
// (args.targetDir, default dashboard/ui-next/); NEVER edits the live dashboard/static/index.html until
// the operator promotes. Cannot block ship-gate. Full IA redesign is ADR-gated -- this workflow REFUSES
// to run until args.adrApproved === true (the ADR amendment to INTENT.md UI principles must land first).
//
// ARGS-DRIVEN (no fs side-effects at author time). Pass:
//   { spec, adrApproved, stack, targetDir, mustConstraints[], shouldConstraints[], endpoints[], concepts }
// where spec = the UI-DESIGN-SPEC.md text (or its distilled MUST/SHOULD list). NEVER run install/build/soak
// inside a subagent (>5min risk) -- the final `npm install && build && axe` is returned as a main-thread gate.
export const meta = {
  name: 'sm-ui-build',
  description: 'KingMode greenfield UI build (EXPERIMENTAL spike, framework+build stack). Judge-panel concept -> worktree-isolated component build -> adversarial multi-lens review -> main-thread build/axe gate. Args-driven; refuses until ADR-approved; never touches the live dashboard.',
  phases: [{ title: 'Concept' }, { title: 'Build' }, { title: 'Review' }, { title: 'Gate' }],
};

// ---- Persona + safety preamble shared by every agent ----
const KINGMODE = [
  'PERSONA: Senior Frontend Architect & Avant-Garde UI Designer (docs/KingModePrompt.txt).',
  'Anti-generic: reject template/bootstrapped layouts. Bespoke, asymmetric, distinctive typography.',
  'Intentional minimalism: every element earns its place or is deleted. Micro-interactions, perfect spacing.',
  'Multi-dimensional: psychological (cognitive load) + technical (repaint/reflow, state) + WCAG AAA + scalability.',
].join('\n');

const SAFETY = [
  'SCOPE: EXPERIMENTAL spike. Write ONLY under the target prototype dir. NEVER edit dashboard/static/index.html,',
  '  dashboard/server.py, or any src/stream_manager/** file. The live dashboard is untouched until operator promotion.',
  'FIREWALL (G1): never read/glob/grep **/certPortal/**. ZERO-CONTAMINATION (G11): the SM UI must contain NO',
  '  monitored-project vocab (certPortal names, JOB-IDs, agent-role names). SM is domain-agnostic; the governed',
  '  project is configuration, not vocabulary. Render governed-target identifiers from data, never hard-code one.',
  'POLARITY (G2): the UI must NEVER present the SM own session as a governed target (default-exclude self).',
  'CONSTRAINT FLOOR: the MUST constraints from the spec are inviolable. KingMode flair may bend SHOULD/MAY,',
  '  never a MUST (e.g. paired label+color badges -- color alone is never a signal; monitor-first default).',
  'LONG-TASK (G7): NEVER run `npm install`, a build, or any >5min command from inside this workflow. Emit it',
  '  as a main-thread gate instead. Subagents that try to install/build are abandoning a long task.',
  'ASCII source discipline (cp1252-safe): no smart quotes / em-dashes / box-drawing in source or docs (-- for dash).',
].join('\n');

// ---- Input resolution ----
// The Workflow tool's `args` global does NOT thread reliably through a scriptPath invocation, so the
// operator-approved payload (ADR-20 Accepted 2026-06-10; UI-DESIGN-SPEC.md SS3 M1-M19) is embedded as
// BUILTIN. `args` still OVERRIDES it when present, so the workflow stays reusable for other specs.
const BUILTIN = {
  adrApproved: true, // ADR-20 Accepted by operator 2026-06-10 via /goal sign-off gate.
  stack: 'Svelte + Tailwind + Vite',
  targetDir: 'dashboard/ui-next/',
  concepts: 4,
  mustConstraints: [
    'M1 3-frame presence: Frame A Interactive REPL/Sessions, Frame B Sub-Agents, Frame C Background Jobs all present at page load, each independently scrollable, layout persisted per-session in localStorage with a Reset control. Arrangement is free; presence is not. (INTENT.md:77-78, REQUIREMENTS.md:378-386)',
    'M2 Escalation-only foreground: only desktop_pause, governance_negative_regression, and static-rule fire auto-foreground a frame; new_pattern / low_confidence / governance_variance_alert flag IN PLACE via badges only. (INTENT.md:79-80, REQUIREMENTS.md:390-399)',
    'M3 Frame + tab action counts: each frame header shows a live open-ACTION-REQUIRED count; browser tab title shows "(N) StreamManager" total, SSE-driven with ~100ms debounce. (REQUIREMENTS.md:445)',
    'M4 Paired label+color badges ALWAYS -- color alone is NEVER a signal. Labels: ACTION REQUIRED, OBSERVING, DECIDED, BLOCKED, WARN, TIMEOUT. Each badge carries title/aria-label = trigger reason. ACTION REQUIRED = amber #d97706 on #fef3c7 with 2px solid amber pulsing border; OBSERVING = slate, no border. Reject any color-without-text rule. (INTENT.md:85-86, REQUIREMENTS.md:432-443)',
    'M5 Two HITL modes SYNC (hold) and ASYNC (decide+annotate), switchable at runtime; switch emits hitl_mode_promoted; UI exposes SYNC/ASYNC only (no off). (REQUIREMENTS.md:314-316)',
    'M6 HITL ON = ranked options: pending rows render APPROVE / OVERRIDE (ranked list or free text) / DISMISS; selection persisted keyed to message hash for reinforcement. (INTENT.md:81-82, REQUIREMENTS.md:403-430)',
    'M7 HITL OFF = read-only + opt-in: OFF decisions render read-only with OBSERVING badge + explicit Take action affordance; activating flips session to HITL ON SYNC, surfaces ranked list, persists, emits hitl_mode_promoted. (INTENT.md:83-84)',
    'M8 HITL gate is absolute: Learn-Mode bias only PRE-FILLS as a dashed non-verdict informational chip above action buttons (title "advisory only -- operator decision still required"); never bypasses gate, never toasts, never offers undo. (index.html:3286-3307, governance.py:902-941)',
    'M9 Countdown bars: each pending row shows a 1s-tick countdown (default 60s); on expiry the row gets opacity .35 + grayscale. (index.html:3339-3361)',
    'M10 Optimistic resolve: filter row immediately, POST /api/hitl/resolve {pending_id, resolution}; on error silently restore prior state. (index.html:3380-3426)',
    'M11 Audit-probe ack: render probe rows with radio candidate list + none-of-the-above; validate session_id set; POST /api/sm-probe/ack with brain_id+prompt_hash from the envelope. (index.html:3428-3469)',
    'M12 Canary echo: render nonce + prompt-to-type with countdown; pending->observed (auto-clear 1.5s) / pending->failed (reason); hallucination alerts render with operator-dismiss. (index.html:3240-3279)',
    'M13 Per-agent role badges, independent: Frame B renders role badges (prompt_constructor, developer, code_reviewer, tester, frontend_architect, researcher, strategic_advisor, health_monitor, sub_agent, unknown), active-in-window pinned to top, chronological event chips; NO inter-agent blocking shown or enforced. (REQUIREMENTS.md:230,383)',
    'M14 Frame C lifecycle: render job/agent name, id/PID, status (running/exited), elapsed, exit code; poll /api/lifecycle/jobs every 2s, filter by selected session. (server.py:688-705)',
    'M15 Exclude SM self: read <meta name="sm-own-session-id"> at DOM-ready and filter that session_id from every decision row + mirror (defense-in-depth); empty/missing meta -> skip filtering. (server.py:547-562)',
    'M16 Domain-agnostic: NO monitored-project vocabulary hard-coded anywhere; governed-target identity renders from data only. (CLAUDE.md firewall + zero-contamination)',
    'M17 a11y gate: pass npm run axe (axe-core + puppeteer, WCAG 2.1 A+AA); block on serious/critical (AAA color-contrast-enhanced excluded). Focus rings 2px solid #d97706 + 2px offset on all interactive elements. (axe_audit.mjs:137-160)',
    'M18 Latency budget: UI is post-hoc observability; must NOT add to the verdict hot path or require live per-decision latency reads as a hard dependency; respect ADR-5 (p50<=7s, p95<=15s). (REQUIREMENTS.md:494,556)',
    'M19 Non-goals hold: no general-purpose IDE / terminal multiplexer; no multi-tenant; does not replace Claude Code permission model. (INTENT.md:88-93)',
  ],
  shouldConstraints: [
    'S1 Operator manually verifies session cwd is non-SM + non-firewalled before attaching; UI MAY surface cwd prominently but no auto surface-and-reject is mandated.',
    'S2 Ship a render-validator asserting M1 (3-frame presence) / M4 (paired badges) / M6 (ranked list) / M2 (escalation-only foreground) -- the canonical dashboard regression contract.',
  ],
  endpoints: [
    'GET / (injects sm-own-session-id meta)',
    'SSE /events (decisions + named bus events; 3s fixed reconnect)',
    'GET /api/stats (poll 5s)',
    'GET /api/decisions?limit&session_id (seed)',
    'GET /api/decisions/export (JSONL)',
    'GET /api/decisions/{id}/suggestions (tray)',
    'GET /api/agents?limit&session_id (poll 8s)',
    'GET /api/sessions (selector)',
    'GET /api/sessions/external + /api/sessions/bg-tasks (watcher)',
    'GET /api/lifecycle/jobs?session_id (poll 2s)',
    'GET /api/registry/active',
    'GET /api/hitl/pending?session_id',
    'POST /api/hitl/resolve + /api/hitl/annotate',
    'GET|POST /api/sm-probe?session_id&force=1 + /api/sm-probe/ack',
    'POST /api/sm-canary/emit + /api/sm-decoy/register',
    'GET /api/patterns/cross_session + POST /api/patterns/{hash}/demote',
    'Named SSE events: hitl_sync_queued, hitl_timeout, audit.probe, audit.probe_ack, audit.canary_emit, audit.canary_observed, audit.probe_failure, audit.hallucination_detected, governance_negative_regression, governance_variance_alert, nfr_model_routing_alert',
    'DO NOT confuse /events (dashboard state) with /api/commands/stream (consumer-only; not a dashboard transport)',
  ],
  spec: 'StreamManager operator UI -- KingMode redesign, EXPERIMENTAL spike. RE-ARCHITECTURE not greenfield: the existing dashboard/static/index.html is already feature-complete (3-frame, sidebar Agents/Monitor/Feed/Events, HITL countdown bars, full FR-PPP audit-probe/canary/hallucination UI, settings panel, 3 themes obsidian/phosphor/paper, axe WCAG-AA gate) backed by REQUIREMENTS.md FR-UI-1..9/FR-HITL/FR-AR. Preserve the behavioural contract (every endpoint, SSE event, badge semantic, setting, a11y gate in M1-M19 + endpoints) while restructuring the FORM (frame geometry, hierarchy, motion, density, typography) into something awe-inspiring. Awe lives in the craft layer; the contract layer is frozen. Product: governance+adaptive-learning bridge between Claude Desktop orchestration and a Claude CLI executor (project-manager layer); enforces plan-alignment + cadence; governs messages not transitions; 5 modes OBSERVE/SUGGEST/GUIDE/INTERVENE/BLOCK; L0-L4 decision graph; HITL sync/async with human-override reinforcement; Learn-Mode advisory pre-fill only. Operator: single-user, laptop, claude -p; wants monitor-first calm + glance-readability across concurrent sessions via a header session picker (filters every pane by session_id, localStorage-persisted, default most-recent). Keep the existing Feed 8-col grid (time/action/source/layer/agent/confidence/content+reason/session) with ALL/ALLOW/SUGGEST/GUIDE/INTERVENE/BLOCK filters + MAX_ROWS=300 + JSONL export; Events panel type-color-coded (exact type names); Settings FR-UI-9 (HITL mode, confidence floor, sync timeout, pause detection, audible cue, activity window, reduced-motion, layout reset -> emit dashboard_settings_changed). Keep 3 themes via CSS custom properties; measure+document the paper theme --text-dim contrast before production. Stack Svelte+Tailwind+Vite contained to dashboard/ui-next/ (build artifacts + node_modules git-ignored). Live dashboard/static/index.html + server.py UNTOUCHED; UI consumes the existing server API unchanged. npm install/build/axe are MAIN-THREAD only. Full grounded spec: UI-DESIGN-SPEC.md.',
};

const IN = (args && typeof args === 'object') ? args : BUILTIN;

// ---- Guard: refuse unless ADR-approved + a non-empty MUST floor present ----
if (IN.adrApproved !== true) {
  throw new Error('sm-ui-build: REFUSED -- adrApproved !== true. Full-redesign IA needs ADR-20 (INTENT.md UI principles amendment) Accepted first (operator-locked gate).');
}
const SPEC = String(IN.spec || '').slice(0, 12000);
const STACK = IN.stack || 'Svelte + Tailwind + Vite';
const TARGET = IN.targetDir || 'dashboard/ui-next/';
const MUST = Array.isArray(IN.mustConstraints) ? IN.mustConstraints : [];
const SHOULD = Array.isArray(IN.shouldConstraints) ? IN.shouldConstraints : [];
const ENDPOINTS = Array.isArray(IN.endpoints) ? IN.endpoints : [];
const N_CONCEPTS = Math.max(2, Math.min(4, Number(IN.concepts) || 3));
if (!MUST.length) throw new Error('sm-ui-build: REFUSED -- mustConstraints[] empty. The UI cannot be built without the binding constraint floor from UI-DESIGN-SPEC.md.');

// ---- Schemas ----
const CONCEPT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['angle', 'thesis', 'layout', 'components', 'mustCompliance'],
  properties: {
    angle: { type: 'string' },
    thesis: { type: 'string' },
    layout: { type: 'string' }, // ascii sketch of the IA
    components: { type: 'array', items: { type: 'string' } },
    mustCompliance: { type: 'array', items: { // one row per MUST: how this concept honors it
      type: 'object', additionalProperties: false,
      required: ['must', 'how'], properties: { must: { type: 'string' }, how: { type: 'string' } } } },
    risks: { type: 'array', items: { type: 'string' } },
  },
};
const SCORE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['conceptAngle', 'scores', 'total', 'verdict'],
  properties: {
    conceptAngle: { type: 'string' },
    scores: { type: 'object', additionalProperties: false, required: ['mustCompliance', 'aweFactor', 'scalability', 'operatorFit', 'accessibility'],
      properties: { mustCompliance: { type: 'number' }, aweFactor: { type: 'number' }, scalability: { type: 'number' }, operatorFit: { type: 'number' }, accessibility: { type: 'number' } } },
    total: { type: 'number' },
    verdict: { type: 'string' },
  },
};
const PLAN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['winningAngle', 'rationale', 'fileUnits'],
  properties: {
    winningAngle: { type: 'string' },
    rationale: { type: 'string' },
    fileUnits: { type: 'array', items: { // file-disjoint build units (union-find: no two units share a file)
      type: 'object', additionalProperties: false,
      required: ['unitId', 'files', 'responsibility', 'consumesEndpoints'],
      properties: { unitId: { type: 'string' }, files: { type: 'array', items: { type: 'string' } },
        responsibility: { type: 'string' }, consumesEndpoints: { type: 'array', items: { type: 'string' } } } } },
  },
};
const BUILD_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['unitId', 'filesWritten', 'summary', 'mustHonored'],
  properties: {
    unitId: { type: 'string' },
    filesWritten: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    mustHonored: { type: 'array', items: { type: 'string' } },
    selfFlags: { type: 'array', items: { type: 'string' } },
  },
};
const REVIEW_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['unitId', 'lens', 'verdict', 'findings'],
  properties: {
    unitId: { type: 'string' },
    lens: { type: 'string' },
    verdict: { type: 'string', enum: ['PASS', 'REPAIR', 'BLOCK'] },
    findings: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['severity', 'file', 'problem', 'fix'],
      properties: { severity: { type: 'string', enum: ['BLOCKER', 'MAJOR', 'MINOR'] },
        file: { type: 'string' }, problem: { type: 'string' }, fix: { type: 'string' } } } },
  },
};

const CONSTRAINTS_BLOCK = `SPEC (distilled):\n${SPEC}\n\nMUST constraints (inviolable):\n${MUST.map((m, i) => `  M${i + 1}. ${m}`).join('\n')}\n\nSHOULD constraints (strong preference):\n${SHOULD.map((s, i) => `  S${i + 1}. ${s}`).join('\n')}\n\nEndpoints the UI consumes (preserve the contract):\n${ENDPOINTS.map((e) => `  - ${e}`).join('\n')}\n\nStack: ${STACK}. Target dir (write here only): ${TARGET}`;

// ===== Stage 1: CONCEPT -- N independent KingMode concepts, judged, synthesized into a build plan =====
phase('Concept');
const CONCEPT_ANGLES = [
  'monitor-first-elevated: the INTENT 3-frame IA, but with bespoke density, motion, and typography craft',
  'signal-hero-asymmetric: an asymmetric shell where the highest-severity live signal owns the hero zone, frames reflow around it',
  'ops-command-deck: data-dense command-deck for an operator watching many concurrent governed sessions at a glance',
  'calm-ambient: ambient/calm-tech monitor that stays quiet until a true escalation, maximizing glance-readability',
].slice(0, N_CONCEPTS);

const concepts = (await parallel(CONCEPT_ANGLES.map((angle) => () =>
  agent(`${KINGMODE}\n\n${SAFETY}\n\n${CONSTRAINTS_BLOCK}

Produce ONE distinct UI concept from this angle: "${angle}".
Give: thesis (1-2 sentences), an ASCII layout sketch of the information architecture, the component list,
and a mustCompliance row for EVERY MUST constraint above (how THIS concept honors it -- a concept that
violates any MUST is disqualified, so design around them). List the top risks.`,
    { label: `concept:${angle.split(':')[0]}`, phase: 'Concept', schema: CONCEPT_SCHEMA })
))).filter(Boolean);

const scores = (await parallel(concepts.map((c) => () =>
  agent(`${SAFETY}\n\n${CONSTRAINTS_BLOCK}

Judge this UI concept (be a hard grader). Concept angle: ${c.angle}
Thesis: ${c.thesis}
Layout: ${c.layout}
Components: ${JSON.stringify(c.components)}
MUST-compliance claims: ${JSON.stringify(c.mustCompliance)}

Score 0-10 each: mustCompliance (0 if it violates ANY must), aweFactor, scalability, operatorFit, accessibility(WCAG AAA).
total = sum. Give a one-line verdict. A concept scoring 0 on mustCompliance cannot win regardless of awe.`,
    { label: `judge:${c.angle.split(':')[0]}`, phase: 'Concept', schema: SCORE_SCHEMA })
))).filter(Boolean);

const plan = await agent(`${KINGMODE}\n\n${SAFETY}\n\n${CONSTRAINTS_BLOCK}

Synthesize the FINAL build plan. Concepts: ${JSON.stringify(concepts.map((c) => ({ angle: c.angle, thesis: c.thesis, components: c.components })))}
Judge scores: ${JSON.stringify(scores)}
Pick the highest-total concept that scores >0 on mustCompliance as the spine; GRAFT the best ideas from the
runners-up where they do not conflict with a MUST. Then decompose into file-DISJOINT build units (union-find:
no two units may share a file, so they can be built in parallel worktrees without collision). Each unit names
its files (all under ${TARGET}), its responsibility, and which endpoints it consumes.`,
  { label: 'synthesize-plan', phase: 'Concept', schema: PLAN_SCHEMA });
log(`CONCEPT: ${concepts.length} concepts judged; winner="${plan.winningAngle}"; ${plan.fileUnits.length} file-disjoint build units`);

// ===== Stage 2+3: BUILD -> REVIEW -- pipeline per unit (build in worktree, then multi-lens review) =====
const REVIEW_LENSES = [
  { id: 'a11y', mandate: 'WCAG AAA: contrast >=7:1, full keyboard path, ARIA roles, focus order, reduced-motion, paired label+color badges (color alone is never a signal).' },
  { id: 'perf', mandate: 'Rendering: avoid layout thrash, large reflows, unbatched DOM writes, memory leaks on SSE streams; virtualize long agent/job lists.' },
  { id: 'intent', mandate: 'INTENT compliance: monitor-first default, only true escalations auto-foreground, HITL ON ranked list / OFF read-only, no IDE/multiplexer scope creep, every MUST honored.' },
  { id: 'scale', mandate: 'Flex/scale: graceful on unknown envelope kinds, many concurrent sessions, growing lists, theming/density; clean extension points; no hard-coded governed-target identity (firewall).' },
];

phase('Build');
const built = await pipeline(
  plan.fileUnits,
  // Stage A: build the unit in an isolated worktree (parallel writes cannot collide).
  (unit) => agent(`${KINGMODE}\n\n${SAFETY}\n\n${CONSTRAINTS_BLOCK}

BUILD unit ${unit.unitId}. Winning concept: ${plan.winningAngle}. Plan rationale: ${plan.rationale}
Your files (write ONLY these, all under ${TARGET}): ${JSON.stringify(unit.files)}
Responsibility: ${unit.responsibility}
Endpoints consumed: ${JSON.stringify(unit.consumesEndpoints)}
Write production-grade ${STACK} code with the Write tool to your declared files (all under ${TARGET}).
Honor EVERY MUST. Bespoke + accessible. Return filesWritten + a summary + which MUSTs you honored + any
selfFlags (things a reviewer should double-check).`,
    { label: `build:${unit.unitId}`, phase: 'Build', agentType: 'general-purpose', schema: BUILD_SCHEMA }),
  // Stage B: adversarial multi-lens review of the built unit (each lens blind to the others).
  (build, unit) => parallel(REVIEW_LENSES.map((L) => () =>
    agent(`${SAFETY}\n\n${CONSTRAINTS_BLOCK}

REVIEW unit ${unit.unitId} through the "${L.id}" lens ONLY. Mandate: ${L.mandate}
Files built: ${JSON.stringify(build.filesWritten)}. Builder summary: ${build.summary}
Builder self-flags: ${JSON.stringify(build.selfFlags || [])}
Open the files. One finding per real problem: {severity, file, problem, fix}. No praise, no scope creep.
verdict: PASS (clean) | REPAIR (fixable findings) | BLOCK (a MUST is violated).`,
      { label: `review:${unit.unitId}:${L.id}`, phase: 'Review', agentType: 'Explore', schema: REVIEW_SCHEMA })
  )).then((rs) => ({ unit, build, reviews: rs.filter(Boolean) })),
);

// ===== Stage 4: GATE -- aggregate + return main-thread build/verify handoff (NEVER run install here) =====
phase('Gate');
const units = built.filter(Boolean);
const blocked = units.filter((u) => u.reviews.some((r) => r.verdict === 'BLOCK'));
const needsRepair = units.filter((u) => !blocked.includes(u) && u.reviews.some((r) => r.verdict === 'REPAIR'));
const clean = units.filter((u) => u.reviews.every((r) => r.verdict === 'PASS'));
const allFiles = units.flatMap((u) => u.build.filesWritten || []);
log(`BUILD/REVIEW: ${units.length} units -- clean=${clean.length}, needsRepair=${needsRepair.length}, BLOCKED=${blocked.length}; ${allFiles.length} files written under ${TARGET}`);

return {
  scope: 'EXPERIMENTAL-spike',
  targetDir: TARGET,
  stack: STACK,
  winningAngle: plan.winningAngle,
  units: units.map((u) => ({
    unitId: u.unit.unitId,
    files: u.build.filesWritten,
    verdicts: u.reviews.map((r) => ({ lens: r.lens, verdict: r.verdict })),
    findings: u.reviews.flatMap((r) => r.findings || []),
  })),
  counts: { units: units.length, clean: clean.length, needsRepair: needsRepair.length, blocked: blocked.length, files: allFiles.length },
  // MAIN-THREAD GATE (run from main thread only -- never a subagent; install/build can exceed 5min):
  mainThreadGate: {
    note: 'Run these from the MAIN THREAD via run_in_background + ScheduleWakeup if slow. Do NOT run inside a subagent.',
    steps: [
      `cd ${TARGET} && npm install`,
      `cd ${TARGET} && npm run build`,
      'npm run axe   # WCAG audit via tools/axe_audit.mjs against the served prototype',
    ],
    binaryPass: 'npm run build exit 0 AND axe reports 0 violations of serious/critical impact',
    promotionGate: 'Operator review of the running prototype -> formal v2.x cycle frame to promote ui-next/ over dashboard/static/index.html (sets LOC anchor + surface reclass). This spike CANNOT block ship-gate.',
  },
};
