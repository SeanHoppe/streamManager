// sm-ux-audit -- Operator-value audit workflow (directive #2 + #3 + #4).
// Rosetta-Stone of Claude-ResearchFixWorkflow.md /report-research, recast from "bug report" to
// "does this UI/feature earn its place for the operator?": catalog -> blind dimensional finders
// -> 2-reviewer adversarial refute + adjudicator -> report. SM-native (NO certPortal vocab).
//
// Covers:
//   #2 soak-for-non-SM-sessions    -- the SOAKGAP dimension grounds how soak actually works and
//                                     whether it exercises the live-non-SM-session (learn-mode tail)
//                                     path, polarity-correct, vs the synthetic engine.evaluate pump.
//   #3 operator UX walkthrough     -- the CATALOG emits a main-thread Playwright PLAYBOOK (routes,
//                                     flows, assertions, screenshots). Playwright is NEVER run inside
//                                     a subagent (G7 long-task); the main thread drives it and feeds
//                                     observations back via args.walkthrough on a second pass.
//   #4 deprecation candidates      -- the DEPRECATE dimension flags dead/redundant/superseded/
//                                     never-wired surfaces; survivors become DEPRECATION.md.
//
// READ-ONLY over source + docs. NEVER edits/builds/soaks/launches the server. ASCII-only (cp1252).
// ARGS-DRIVEN (optional): { targetDir, walkthrough[], extraCandidates[] }.
//   walkthrough[] = main-thread Playwright observations [{route, flow, observation, friction, shot}].
//   When empty (first pass), finders work from source + the workflow returns the playbook for the
//   main thread to execute, then re-run with observations populated.
export const meta = {
  name: 'sm-ux-audit',
  description: 'Operator-value audit of the ui-next spike + soak mechanics: catalogs the UI surface, soak-for-non-SM-sessions path, and intent yardstick; ingests main-thread Playwright walkthrough observations; blind dimensional finders (value/friction/deprecate/soak-gap/operator-sense) -> 2-refuter adversarial verify + adjudicator -> survivors + a main-thread Playwright playbook + deprecation list. Read-only; never edits/builds/soaks.',
  phases: [{ title: 'Catalog' }, { title: 'Find' }, { title: 'Verify' }, { title: 'Report' }],
};

const SAFETY = [
  'READ-ONLY. Read/Glob/Grep/Bash(read-only, <=60s) only. NEVER Edit/Write/commit/build/install/launch a server/soak.',
  'FIREWALL (G1): never read/glob/grep **/certPortal/** or C:/Users/SeanHoppe/VS/certPortal/**.',
  '  A fired deny is surfaced, never worked around. SM source that textually references certPortal is fine.',
  'POLARITY (G2): SM monitors NON-SM sessions, never itself. Any session/decision row read includes iff',
  '  project_slug NOT IN {streamManager} AND session_id != self. When you audit the soak path, VERIFY this',
  '  exclusion is actually enforced; a soak that ingests SM-self rows is a SOAKGAP finding, not normal.',
  'ZERO-CONTAMINATION (G11): introduce NO certPortal/monitored-project vocab, JOB-IDs, or role names.',
  '  ASCII-only output (cp1252): no smart quotes, no em-dashes (write --), no box-drawing, no section-sign.',
  'LONG-TASK (G7): NEVER run Playwright, a soak, npm install/build, or any >5min command. The walkthrough',
  '  is emitted as a main-thread PLAYBOOK; you only PLAN it and reason over observations passed in args.',
  'EVERY claim needs >=1 grounding path file:line. A claim with no cited file is a FAIL -- drop it.',
  'Output STRUCTURED data only (the schema). No prose preamble.',
].join('\n');

const IN = (args && typeof args === 'object') ? args : {};
const TARGET = IN.targetDir || 'dashboard/ui-next/';
const WALKTHROUGH = Array.isArray(IN.walkthrough) ? IN.walkthrough.slice(0, 60) : [];
const EXTRA = Array.isArray(IN.extraCandidates) ? IN.extraCandidates.slice(0, 40) : [];
const HAS_WALK = WALKTHROUGH.length > 0;

// ---- CORPUS: the surfaces under audit + the yardsticks that define "value" ----
const CORPUS = [
  { id: 'U1', area: 'ui-next-surface', frontendCode: true,
    glob: `${TARGET}src/App.svelte, ${TARGET}src/lib/components/*.svelte, ${TARGET}src/lib/*.js, ${TARGET}src/lib/stores/*.js, ${TARGET}README.md, ${TARGET}REPAIR-LOG.md`,
    dims: ['frontend-reality', 'value', 'deprecate'] },
  { id: 'U2', area: 'live-dashboard-contract', frontendCode: true,
    glob: 'dashboard/static/index.html, dashboard/server.py',
    dims: ['frontend-reality', 'value', 'deprecate'] },
  { id: 'U3', area: 'soak-mechanics',
    glob: 'tools/soak_driver.py, tools/soak_sse_consumer.py, tools/cassette_record.py, tools/cassette_replay.py, docs/soak-trigger-matrix.md, docs/adr/ADR-17-soak-tiers.md, docs/learn-mode-design.md, src/stream_manager/project_context.py',
    dims: ['soak-gap'] },
  { id: 'U4', area: 'intent-yardstick',
    glob: 'INTENT.md, REQUIREMENTS.md, UI-DESIGN-SPEC.md, MEMORY.md, docs/v10-mvp-status.md, docs/KingModePrompt.txt',
    dims: ['value', 'operator-sense', 'frontend-reality'] },
];

// ---- DIMENSIONS: five blind finders, by-kind not by-luck ----
const DIMS = [
  { id: 'VALUE', dim: 'value',
    hint: 'For each rendered surface/feature in ui-next + the live dashboard, does it deliver concrete OPERATOR value (monitor-first calm, glance-readability across concurrent governed sessions, HITL pick-and-persist)? A feature that is present but adds no decision-value to a laptop operator running `claude -p` is a candidate FRICTION or DEPRECATE. Cite INTENT/REQUIREMENTS where the value is (or is not) anchored. disposition KEEP|ENHANCE|FRICTION|DEPRECATE.' },
  { id: 'FRICTION', dim: 'friction',
    hint: 'What in the UI would confuse or over-load the operator, or simply does not make sense? Redundant panes showing the same data, ambiguous badges, hidden affordances, modal overload, color-only signals (a MUST violation), things that demand attention without being a true escalation. Use the walkthrough observations heavily if present. disposition FRICTION|ENHANCE|KEEP.' },
  { id: 'DEPRECATE', dim: 'deprecate',
    hint: 'Hunt dead/redundant/superseded/never-wired surfaces -- in BOTH ui-next AND the live dashboard. A component that no parent mounts, an endpoint no client calls, a setting that emits no event, a pane duplicated by another, a stale doc claim. CRITICAL: do NOT flag something load-bearing -- before proposing DEPRECATE, trace its wiring (who imports/mounts/calls it). >=2 evidence paths: the definition AND the absence-of-caller. disposition DEPRECATE|KEEP. This is the #4 deliverable; be rigorous, the adjudicator will reject an ungrounded DEPRECATE.' },
  { id: 'SOAKGAP', dim: 'soak-gap',
    hint: 'How does the soak process work for NON-SM sessions? Ground the answer: soak_driver.py pumps SYNTHETIC engine.evaluate load (50 ALLOW + 5 L2/L3 + 5 L4) across 3 tiers (replay/smoke/ship-gate per ADR-17). The genuine "non-SM session" requirement (live local Claude CLI session in a non-SM project, JSONL-tailed by learn-mode, polarity-excluded project_slug != streamManager) is a SEPARATE path. GAPS to surface: does any soak tier actually exercise the live-non-SM-session tail path, or only synthetic? is the polarity exclusion enforced at the soak/ingest seam? what would a real non-SM-session soak need that does not exist? disposition GAP|KEEP|ENHANCE. Cite file:line in soak_driver/cassette/learn-mode/project_context.' },
  { id: 'OPSENSE', dim: 'operator-sense',
    hint: 'Step into Sean: single-user, laptop, `claude -p`, no API-key path, monitor-first, wants calm + glance-readability, fears interruption. Would he actually USE each surface in anger, or is it engineering for its own sake? What is the ONE thing he needs that is missing or buried? disposition ENHANCE|FRICTION|KEEP|DEPRECATE. Anchor in MEMORY.md / user_profile / INTENT operator principles.' },
];

// ---- Schemas ----
const CATALOG_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['area', 'inventory', 'signals'],
  properties: {
    area: { type: 'string' },
    inventory: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['path', 'kind', 'status'],
      properties: { path: { type: 'string' }, kind: { type: 'string' },
        status: { type: 'string', enum: ['live', 'stale', 'dead', 'unknown'] },
        wiredBy: { type: 'string' } } } },
    signals: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['dim', 'path', 'signal'],
      properties: { dim: { type: 'string' }, path: { type: 'string' }, line: { type: 'string' }, signal: { type: 'string' } } } },
  },
};

const FIND_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['dim', 'findings'],
  properties: {
    dim: { type: 'string' },
    findings: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['id', 'dim', 'surface', 'claim', 'grounding', 'disposition', 'severity', 'rationale'],
      properties: {
        id: { type: 'string' },
        dim: { type: 'string' },
        surface: { type: 'string' }, // the component/endpoint/feature under judgment
        claim: { type: 'string' },
        grounding: { type: 'array', items: { type: 'string' } }, // file:line, >=1 (>=2 for DEPRECATE)
        disposition: { type: 'string', enum: ['KEEP', 'ENHANCE', 'FRICTION', 'DEPRECATE', 'GAP'] },
        severity: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
        rationale: { type: 'string' },
        valueArgument: { type: 'string' }, // why the operator does/does-not gain from it
      },
    } },
  },
};

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['findingId', 'verdict', 'evidence'],
  properties: {
    findingId: { type: 'string' },
    verdict: { type: 'string', enum: ['CONFIRM', 'OVERSTATED', 'REFUTED'] },
    evidence: { type: 'string' },
  },
};

const VETTED_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'dim', 'surface', 'claim', 'survives', 'grounding', 'disposition', 'severity'],
  properties: {
    id: { type: 'string' },
    dim: { type: 'string' },
    surface: { type: 'string' },
    claim: { type: 'string' },
    survives: { type: 'boolean' },
    grounding: { type: 'array', items: { type: 'string' } },
    disposition: { type: 'string', enum: ['KEEP', 'ENHANCE', 'FRICTION', 'DEPRECATE', 'GAP'] },
    severity: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
    rationale: { type: 'string' },
    valueArgument: { type: 'string' },
    refuteSummary: { type: 'string' },
  },
};

const PLAYBOOK_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['launch', 'flows'],
  properties: {
    launch: { type: 'array', items: { type: 'string' } }, // main-thread shell steps to bring the UI up
    flows: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['id', 'route', 'asOperator', 'steps', 'assert', 'screenshot'],
      properties: {
        id: { type: 'string' },
        route: { type: 'string' },
        asOperator: { type: 'string' }, // the operator intent this flow simulates
        steps: { type: 'array', items: { type: 'string' } },
        assert: { type: 'array', items: { type: 'string' } }, // what "adds value / makes sense" looks like
        screenshot: { type: 'string' }, // suggested filename under reports/
      },
    } },
    notes: { type: 'string' },
  },
};

// ---- Helpers ----
function findKey(f) {
  const g = (f.grounding && f.grounding[0]) || '';
  const s = (f.surface || '').slice(0, 40).toLowerCase().trim();
  return `${f.dim}|${g}|${s}`;
}
function groupSignalsByDim(catalogues) {
  const byDim = {};
  for (const cat of catalogues) for (const s of (cat.signals || [])) (byDim[s.dim] = byDim[s.dim] || []).push(s);
  return byDim;
}
function dedupeByKey(items) {
  const seen = new Map();
  for (const f of items) { const k = findKey(f); if (!seen.has(k)) seen.set(k, f); }
  return [...seen.values()];
}

// ===== Stage 1: CATALOG -- one cataloguer per surface cluster + one walkthrough-planner (barrier) =====
phase('Catalog');
const catalogTasks = CORPUS.map((a) => () =>
  agent(`${SAFETY}

Cataloguer for cluster ${a.id} (${a.area}). Globs: ${a.glob}
Inventory every matching artefact: {path, kind, status=live|stale|dead|unknown, wiredBy=who imports/mounts/calls it (or "NONE FOUND")}.
${a.frontendCode ? 'FRONTEND cluster: read the Svelte/HTML/py enough to know what each component/pane RENDERS, what data it consumes, and CRUCIALLY who mounts/imports it (trace the import graph from App.svelte / main.js). A component imported by no parent is a dead-surface signal. ' : ''}${a.id === 'U3' ? 'SOAK cluster: extract exactly how the soak pumps load, the 3 tiers, and whether ANY path tails a live non-SM Claude session vs synthetic engine.evaluate. Note where polarity (project_slug != streamManager) is or is not enforced. ' : ''}Extract candidate signals for dimensions [${a.dims.join(', ')}]. Each signal = {dim, path, line, signal} with a real file:line.
Return inventory + signals.`,
    { label: `catalog:${a.id}`, phase: 'Catalog', agentType: 'Explore', schema: CATALOG_SCHEMA }));

// walkthrough-planner: produces the main-thread Playwright playbook (NEVER runs Playwright itself).
const playbookTask = () => agent(`${SAFETY}

Walkthrough PLANNER. Produce a Playwright PLAYBOOK the MAIN THREAD will run (you do NOT run it).
Read ${TARGET}README.md + dashboard/server.py to learn how to launch the dashboard server and serve the
built ui-next (dist/). The operator UI is a governance MONITOR; the playbook must drive it AS IF you are
Sean: glance at concurrent sessions, read decisions, handle a HITL pending row, inspect sub-agents + jobs,
toggle a setting, switch theme. For each flow give: route, the operator intent (asOperator), concrete steps
(playwright actions), assertions that capture "does this add value / make sense", and a screenshot filename
under reports/. launch[] = the exact shell steps (server up + npx playwright). Keep flows <=8, each runnable
in well under 5 minutes so the main thread stays inside the long-task budget.`,
  { label: 'catalog:playbook', phase: 'Catalog', agentType: 'Explore', schema: PLAYBOOK_SCHEMA });

const catResults = (await parallel([...catalogTasks, playbookTask])).filter(Boolean);
const playbook = catResults.find((r) => r && Array.isArray(r.flows)) || { launch: [], flows: [], notes: 'planner returned nothing' };
const catalogues = catResults.filter((r) => r && Array.isArray(r.inventory));
const signalsByDim = groupSignalsByDim(catalogues);
log(`CATALOG: ${catalogues.length}/${CORPUS.length} clusters inventoried; playbook flows=${playbook.flows.length}; `
  + `walkthrough observations supplied=${WALKTHROUGH.length}; `
  + `${Object.values(signalsByDim).reduce((n, a) => n + a.length, 0)} signals`);

// ===== Stage 2: FIND -- one blind finder per dimension (barrier) =====
phase('Find');
const WALK_BLOCK = HAS_WALK
  ? `\nMAIN-THREAD WALKTHROUGH OBSERVATIONS (operator-driven Playwright, treat as evidence):\n${JSON.stringify(WALKTHROUGH)}\n`
  : `\n(No live walkthrough observations supplied this pass -- reason from source. The main thread will run the playbook and re-run this workflow with args.walkthrough populated for a value-judgment grounded in rendered reality.)\n`;
const EXTRA_BLOCK = EXTRA.length ? `\nOperator-supplied extra candidates to evaluate: ${JSON.stringify(EXTRA)}\n` : '';

const rawFindings = (await parallel(DIMS.map((d) => () =>
  agent(`${SAFETY}

Blind finder for dimension "${d.dim}" (${d.id}). You judge whether the UI/soak surfaces EARN their place.
WHAT TO FIND: ${d.hint}
${WALK_BLOCK}${EXTRA_BLOCK}
Cataloguer signals pre-tagged for you (may be empty -- sweep the cited files yourself, do NOT stop here): ${JSON.stringify((signalsByDim[d.dim] || []).slice(0, 50))}

Open the cited files. Produce distinct, NON-overlapping findings. QUALITY BAR (reject below it):
each finding needs >=1 grounding file:line (>=2 for a DEPRECATE: the definition AND the absence-of-caller),
a concrete valueArgument, root cause over symptom. id globally unique e.g. "${d.id}-<n>".`,
    { label: `find:${d.id}`, phase: 'Find', agentType: 'Explore', schema: FIND_SCHEMA })
))).filter(Boolean).flatMap((r) => (r.findings || []).map((f) => ({ ...f, dim: r.dim })));
const findings = dedupeByKey(rawFindings);
log(`FIND: ${rawFindings.length} raw -> ${findings.length} deduped across ${DIMS.length} dimensions`);

// ===== Stage 3: VERIFY -- 2 isolated refuters + adjudicator per finding (pipeline, no barrier) =====
const VERIFY_CAP = 70;
const toVerify = findings.slice(0, VERIFY_CAP);
if (findings.length > VERIFY_CAP) {
  log(`VERIFY cap: ${findings.length} findings; verifying first ${VERIFY_CAP}, `
    + `${findings.length - VERIFY_CAP} DEFERRED (logged, not silently dropped) -- re-run to cover them`);
}

phase('Verify');
const vetted = await pipeline(
  toVerify,
  (f) => parallel([
    () => agent(`${SAFETY}

Refuter A for finding ${f.id} [dim=${f.dim}, disposition=${f.disposition}]. REFUTE, do not agree.
Surface: ${f.surface}
Claim: ${f.claim}
Grounding cited: ${JSON.stringify(f.grounding)}
Value argument: ${f.valueArgument || ''}
Open the cited files. Hunt a contradiction: the file does not say this; the cite is stale vs HEAD; the
disposition over-reaches. For a DEPRECATE specifically: PROVE it is genuinely dead -- if you find ANY parent
that mounts/imports/calls the surface, REFUTE (do not let a load-bearing surface be marked dead).
Return CONFIRM | OVERSTATED (real but inflated -- say what) | REFUTED (cite the contradicting file:line).`,
      { label: `refute:${f.id}:A`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA }),
    () => agent(`${SAFETY}

Refuter B for finding ${f.id} [dim=${f.dim}, disposition=${f.disposition}]. ISOLATED from A. Same REFUTE mandate.
Surface: ${f.surface}
Claim: ${f.claim}
Grounding cited: ${JSON.stringify(f.grounding)}
Independently open the cited files. Is the claim + disposition actually supported? For DEPRECATE, independently
grep for callers/mounts before agreeing it is dead.
Return CONFIRM | OVERSTATED | REFUTED with a file:line.`,
      { label: `refute:${f.id}:B`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA }),
  ]).then((v) => v.filter(Boolean)),
  (verdicts, f) => agent(`${SAFETY}

Adjudicator for finding ${f.id} [dim=${f.dim}, disposition=${f.disposition}].
Surface: ${f.surface}
Claim: ${f.claim}
Grounding: ${JSON.stringify(f.grounding)}
Value argument: ${f.valueArgument || ''}
Refuter verdicts: ${JSON.stringify(verdicts)}

DECISION RULE: survives=false ONLY on a decisive REFUTED backed by a real file:line contradiction.
OVERSTATED -> survives=true but tighten claim + disposition to exactly what grounding supports
  (e.g. a refuted DEPRECATE that is actually wired downgrades to ENHANCE or KEEP -- never keep a wrong DEPRECATE).
CONFIRM -> survives=true. Stamp ALL fields; keep >=1 real file:line; refuteSummary = one line on what the refuters found.`,
    { label: `adjudicate:${f.id}`, phase: 'Verify', agentType: 'Explore', schema: VETTED_SCHEMA }),
);

// ===== Stage 4: REPORT -- survivors + playbook to MAIN THREAD =====
const survivors = vetted.filter(Boolean).filter((c) => c.survives);
const byDisp = survivors.reduce((m, c) => { m[c.disposition] = (m[c.disposition] || 0) + 1; return m; }, {});
const byDim = survivors.reduce((m, c) => { m[c.dim] = (m[c.dim] || 0) + 1; return m; }, {});
log(`VERIFY: ${survivors.length}/${toVerify.length} survived adversarial refute `
  + `(KEEP=${byDisp.KEEP || 0}, ENHANCE=${byDisp.ENHANCE || 0}, FRICTION=${byDisp.FRICTION || 0}, DEPRECATE=${byDisp.DEPRECATE || 0}, GAP=${byDisp.GAP || 0})`);

phase('Report');
return {
  scope: 'EXPERIMENTAL-spike-audit',
  walkthroughSupplied: HAS_WALK,
  counts: {
    cataloguers: catalogues.length,
    rawFindings: rawFindings.length,
    deduped: findings.length,
    verified: toVerify.length,
    deferred: Math.max(0, findings.length - VERIFY_CAP),
    survivors: survivors.length,
    byDisposition: byDisp,
    byDim,
  },
  inventory: catalogues.flatMap((c) => (c.inventory || []).map((i) => ({ ...i, area: c.area }))),
  survivors,
  // For DEPRECATION.md (#4):
  deprecate: survivors.filter((s) => s.disposition === 'DEPRECATE'),
  // For the soak-for-non-SM-sessions write-up (#2):
  soakGaps: survivors.filter((s) => s.dim === 'soak-gap'),
  // MAIN-THREAD Playwright walkthrough (#3) -- run from the main thread, NEVER a subagent (G7):
  mainThreadWalkthrough: {
    note: 'Run from MAIN THREAD. Bring the server up, run npx playwright per flow, capture screenshots, then '
      + 're-run sm-ux-audit with args.walkthrough = the observations for a rendered-reality value judgment.',
    playbook,
  },
};
