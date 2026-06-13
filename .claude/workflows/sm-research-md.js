// sm-research-md -- Research workflow (directive #1). Rosetta-Stone of Claude-ResearchFixWorkflow.md:
//   catalog -> blind dimensional finders -> 2-reviewer adversarial refute + adjudicator -> report.
// BUT the output contract here is an INTENT MAP + FRONTEND AUDIT (grounding for UI-DESIGN-SPEC.md),
// not a bug report. Fans out read-only cataloguers over every *.md cluster + the live dashboard
// frontend code, extracts intent/UI/operator signals, then refuters reject any claim NOT grounded in
// a cited file:line (kills hallucinated intent). Survivors return to MAIN THREAD, which writes
// UI-DESIGN-SPEC.md. READ-ONLY. NEVER edits, builds, soaks. ASCII-only (cp1252).
export const meta = {
  name: 'sm-research-md',
  description: 'Read-only research over every *.md cluster + the dashboard frontend code; extracts a grounded intent map + frontend audit (survivors) for the main thread to write UI-DESIGN-SPEC.md. Never edits/builds/soaks.',
  phases: [{ title: 'Catalog' }, { title: 'Synthesize' }, { title: 'Verify' }, { title: 'Report' }],
};

const SAFETY = [
  'READ-ONLY. Read/Glob/Grep/Bash(read-only, <=60s) only. NEVER Edit/Write/commit/build/install.',
  'FIREWALL (G1): never read/glob/grep **/certPortal/** or C:/Users/SeanHoppe/VS/certPortal/**.',
  '  A fired deny is surfaced, never worked around. SM source that textually references certPortal is fine.',
  'POLARITY (G2): this workflow reads md + frontend source, not gov.db corpus. If you DO read any',
  '  session/decision row, INCLUDE iff project_slug NOT IN {streamManager} AND session != self. N/A here normally.',
  'ZERO-CONTAMINATION (G11): introduce NO certPortal vocab/JOB-IDs/roles. ASCII-only output (cp1252):',
  '  no smart quotes, no em-dashes (write --), no box-drawing, no section-sign.',
  'EVERY claim needs >=1 grounding path file:line. A claim with no cited file is a FAIL -- drop it.',
  'Output STRUCTURED data only (the schema). No prose preamble.',
].join('\n');

// ---- CORPUS map: targeted *.md clusters + the live frontend code (NOT 519-file exhaustive) ----
// Each cluster is catalogued by one read-only Explore agent. The frontend cluster (I4) reads the
// actual dashboard so the audit is grounded in rendered reality, not doc claims about it.
const CORPUS = [
  { id: 'I1', area: 'anchor-intent',
    glob: 'INTENT.md, REQUIREMENTS.md, CLAUDE.md, MEMORY.md, README.md, CONTRIBUTING.md, CHANGELOG.md, smartai.md',
    dims: ['product-intent', 'operator-profile', 'ui-hitl-principles', 'design-constraints'] },
  { id: 'I2', area: 'adr-governance',
    glob: 'docs/adr/ADR-*.md',
    dims: ['design-constraints', 'ui-hitl-principles', 'scale-flex-needs'] },
  { id: 'I3', area: 'design-roadmap',
    glob: 'docs/*design*.md, docs/*learn-mode*.md, docs/v10-mvp-status.md, docs/v*-task-plan.md, streamManagerworkflow.md, Claude-ResearchFixWorkflow.md, MVP-GAP-REPORT.md',
    dims: ['product-intent', 'scale-flex-needs', 'design-constraints'] },
  { id: 'I4', area: 'frontend-code',
    glob: 'dashboard/static/index.html, dashboard/server.py, dashboard/requirements.txt, package.json, tools/axe_audit.mjs',
    dims: ['frontend-code-reality', 'ui-hitl-principles', 'scale-flex-needs'], frontendCode: true },
  { id: 'I5', area: 'hitl-operator-ux',
    glob: 'docs/*hitl*.md, docs/prompts/**/*.md, docs/KingModePrompt.txt, docs/*ux*.md, docs/*dashboard*.md',
    dims: ['operator-profile', 'ui-hitl-principles', 'design-constraints'] },
  { id: 'I6', area: 'reports-ui-signal',
    glob: 'reports/poc-*.md, reports/*dashboard*.md, reports/*ui*.md, docs/2026-*-task-list.md',
    dims: ['frontend-code-reality', 'operator-profile', 'scale-flex-needs'], readEvidenceOnly: true },
];

// ---- DIMENSIONS: six blind synthesizers. Each extracts grounded signal of one kind. ----
const DIMS = [
  { id: 'D1', dim: 'product-intent',
    hint: 'What SM actually IS and the value it delivers: a domain-agnostic governance+adaptive-learning bridge between Desktop sub-agent orchestration and a Claude CLI executor; enforces plan-alignment + cadence; governs messages not transitions; per-role agent governance; safety floor. Extract the job-to-be-done the UI must serve.' },
  { id: 'D2', dim: 'operator-profile',
    hint: 'WHO the operator is and what they need/want/fear. Sean: runs governance on a laptop via `claude -p`, no API-key path; monitor-first (see activity without being interrupted); glance-readability; HITL pick-and-persist. Extract needs, wants, pains, and the cognitive-load budget the UI must respect.' },
  { id: 'D3', dim: 'ui-hitl-principles',
    hint: 'The BINDING UI rules. INTENT.md UI/HITL principles: monitor-first 3-frame (Interactive REPL, Sub-Agents, Background Jobs); only true escalations (desktop_pause, negative regression, static-rule fire) auto-foreground; lower signals flag in place via PAIRED label+color badges (color alone is NOT a signal); HITL ON = ranked option list, persist pick; HITL OFF = read-only proposed answer + per-card opt-in. Cite every rule with its file:line so the spec cannot drift from it.' },
  { id: 'D4', dim: 'frontend-code-reality',
    hint: 'What the EXISTING dashboard actually is. Read dashboard/static/index.html + server.py: enumerate the API/SSE endpoints the UI consumes (/api/stats, /api/decisions, /api/agents, /api/sessions[/external|/bg-tasks], /api/lifecycle/jobs, /api/hitl/*, /api/sm-probe*, /api/patterns/*, the SSE stream), the frames rendered, the client state model, theming, and the a11y posture (axe tooling). Note gaps vs the INTENT 3-frame + badge spec. This is the contract the new UI must preserve.' },
  { id: 'D5', dim: 'design-constraints',
    hint: 'The hard limits any UI must obey. ADR-18 surface classes (dashboard/* is EVOLVING; this build is an EXPERIMENTAL spike on a separate path); certPortal dev-firewall + zero-contamination (no monitored-project vocab in SM UI); polarity-flip (SM never renders its own session as a governed target); INTENT non-goals (no IDE/multiplexer, no multi-tenant); ASCII discipline. Also the KingMode design philosophy (anti-generic, bespoke, asymmetry, intentional minimalism, WCAG AAA) and how it RECONCILES with the prescriptive 3-frame IA.' },
  { id: 'D6', dim: 'scale-flex-needs',
    hint: 'What "flexible and scalable" must concretely mean here: many concurrent governed sessions; growing sub-agent + background-job lists; new bus envelope kinds added per cycle (the UI must degrade gracefully on unknown kinds); theming/density modes; live SSE volume; future non-Claude CLI targets (architecture allows, v1 does not). Extract the extension points the UI architecture must expose.' },
];

// ---- Schemas ----
const CATALOG_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['area', 'inventory', 'signals'],
  properties: {
    area: { type: 'string' },
    inventory: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['path', 'kind', 'status'],
        properties: {
          path: { type: 'string' },
          kind: { type: 'string' },
          status: { type: 'string', enum: ['live', 'stale', 'dead', 'unknown'] },
        },
      },
    },
    signals: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['dim', 'path', 'signal'],
        properties: {
          dim: { type: 'string' },
          path: { type: 'string' },
          line: { type: 'string' },
          signal: { type: 'string' },
        },
      },
    },
  },
};

const SYNTH_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['dim', 'claims'],
  properties: {
    dim: { type: 'string' },
    claims: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'dim', 'claim', 'grounding', 'uiImplication'],
        properties: {
          id: { type: 'string' },
          dim: { type: 'string' },
          claim: { type: 'string' },
          grounding: { type: 'array', items: { type: 'string' } }, // file:line cites, >=1
          uiImplication: { type: 'string' }, // what this means for the new UI
          confidence: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
        },
      },
    },
  },
};

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['claimId', 'verdict', 'evidence'],
  properties: {
    claimId: { type: 'string' },
    verdict: { type: 'string', enum: ['CONFIRM', 'OVERSTATED', 'REFUTED'] },
    evidence: { type: 'string' },
  },
};

const VETTED_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'dim', 'claim', 'survives', 'grounding', 'uiImplication', 'binding'],
  properties: {
    id: { type: 'string' },
    dim: { type: 'string' },
    claim: { type: 'string' },
    survives: { type: 'boolean' },
    grounding: { type: 'array', items: { type: 'string' } },
    uiImplication: { type: 'string' },
    binding: { type: 'string', enum: ['MUST', 'SHOULD', 'MAY'] }, // is this a hard constraint or a preference
    confidence: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
    refuteSummary: { type: 'string' },
  },
};

// ---- Helpers ----
function claimKey(c) {
  const g = (c.grounding && c.grounding[0]) || '';
  const s = (c.claim || '').slice(0, 50).toLowerCase().replace(/\s+/g, ' ').trim();
  return `${c.dim}|${g}|${s}`;
}
function groupSignalsByDim(catalogues) {
  const byDim = {};
  for (const cat of catalogues) {
    for (const s of (cat.signals || [])) (byDim[s.dim] = byDim[s.dim] || []).push(s);
  }
  return byDim;
}
function dedupeByKey(claims) {
  const seen = new Map();
  for (const c of claims) { const k = claimKey(c); if (!seen.has(k)) seen.set(k, c); }
  return [...seen.values()];
}

// ===== Stage 1: CATALOG -- one read-only cataloguer per cluster (barrier; synthesizers need the map) =====
phase('Catalog');
const catalogues = (await parallel(CORPUS.map((a) => () =>
  agent(`${SAFETY}

Cataloguer for cluster ${a.id} (${a.area}). Globs: ${a.glob}
Inventory every matching artefact: {path, kind, status=live|stale|dead|unknown}.
${a.frontendCode ? 'FRONTEND CODE cluster: this is the LIVE dashboard. Read index.html + server.py fully enough to enumerate (a) every API/SSE endpoint the client calls, (b) the frames/sections rendered, (c) the client state + SSE wiring, (d) theming + a11y posture. Each becomes a signal with a file:line. ' : ''}${a.readEvidenceOnly ? 'EVIDENCE-ONLY: read existing report files as FROZEN evidence; NEVER trigger a soak/eval/build. ' : ''}Extract candidate signals for these dimensions: [${a.dims.join(', ')}].
Each signal = {dim, path, line, signal}: a concrete, citable fact relevant to building the new operator UI.
Every signal MUST carry a real file:line. Return inventory + signals.`,
    { label: `catalog:${a.id}`, phase: 'Catalog', agentType: 'Explore', schema: CATALOG_SCHEMA })
))).filter(Boolean);
const signalsByDim = groupSignalsByDim(catalogues);
log(`CATALOG: ${catalogues.length}/${CORPUS.length} clusters inventoried; `
  + `${Object.values(signalsByDim).reduce((n, a) => n + a.length, 0)} signals across ${Object.keys(signalsByDim).length} dimensions`);

// ===== Stage 2: SYNTHESIZE -- one blind synthesizer per dimension (barrier) =====
phase('Synthesize');
const rawClaims = (await parallel(DIMS.map((d) => () =>
  agent(`${SAFETY}

Blind synthesizer for dimension "${d.dim}" (${d.id}). You are building the grounded basis of a UI design spec.
WHAT TO EXTRACT: ${d.hint}
Cataloguer signals pre-tagged for your dimension (may be empty -- do NOT stop at these; sweep the cited files yourself): ${JSON.stringify((signalsByDim[d.dim] || []).slice(0, 50))}

Open the cited files and produce distinct, NON-overlapping claims. QUALITY BAR (reject below it):
each claim needs >=1 grounding path (file:line) AND a concrete uiImplication (what the new UI must do as a result).
id globally unique, e.g. "${d.id}-<n>". Mark confidence HIGH only when the grounding is explicit text, not inference.`,
    { label: `synth:${d.id}`, phase: 'Synthesize', agentType: 'Explore', schema: SYNTH_SCHEMA })
))).filter(Boolean).flatMap((r) => (r.claims || []).map((c) => ({ ...c, dim: r.dim })));
const claims = dedupeByKey(rawClaims);
log(`SYNTHESIZE: ${rawClaims.length} raw claims -> ${claims.length} deduped across ${DIMS.length} dimensions`);

// ===== Stage 3: VERIFY -- 2 isolated refuters + adjudicator per claim (pipeline, no barrier) =====
const VERIFY_CAP = 60;
const toVerify = claims.slice(0, VERIFY_CAP);
if (claims.length > VERIFY_CAP) {
  log(`VERIFY cap: ${claims.length} claims; verifying first ${VERIFY_CAP}, `
    + `${claims.length - VERIFY_CAP} DEFERRED (logged, not silently dropped) -- re-run to cover them`);
}

phase('Verify');
const vetted = await pipeline(
  toVerify,
  (claim) => parallel([
    () => agent(`${SAFETY}

Refuter A for claim ${claim.id} [dim=${claim.dim}]. Your job is to REFUTE, not agree.
Claim: ${claim.claim}
Grounding cited: ${JSON.stringify(claim.grounding)}
UI implication asserted: ${claim.uiImplication}
Open the cited files. Hunt a contradiction: the file does NOT say this; the cite is stale vs HEAD; the
claim over-reaches the text; the uiImplication does not follow from the grounding.
Return CONFIRM (claim is grounded -- cite the line) | OVERSTATED (partly true -- say exactly what over-reaches) |
REFUTED (the grounding does not support it -- cite file:line).`,
      { label: `refute:${claim.id}:A`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA }),
    () => agent(`${SAFETY}

Refuter B for claim ${claim.id} [dim=${claim.dim}]. ISOLATED from refuter A. Same REFUTE mandate.
Claim: ${claim.claim}
Grounding cited: ${JSON.stringify(claim.grounding)}
Independently open the cited files. Is the claim actually supported by the text at those lines?
Return CONFIRM | OVERSTATED | REFUTED with a file:line.`,
      { label: `refute:${claim.id}:B`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA }),
  ]).then((v) => v.filter(Boolean)),
  (verdicts, claim) => agent(`${SAFETY}

Adjudicator for claim ${claim.id} [dim=${claim.dim}].
Claim: ${claim.claim}
Grounding: ${JSON.stringify(claim.grounding)}
UI implication: ${claim.uiImplication}
Refuter verdicts: ${JSON.stringify(verdicts)}

DECISION RULE: survives=false ONLY on a decisive REFUTED backed by a real file:line contradiction.
OVERSTATED -> survives=true but tighten the claim + uiImplication to exactly what the grounding supports.
CONFIRM -> survives=true. If it survives, stamp ALL fields:
- binding: MUST (a hard constraint -- INTENT/REQUIREMENTS/ADR/firewall rule the UI cannot violate) |
           SHOULD (strong operator preference grounded in MEMORY/feedback/design docs) |
           MAY (nice-to-have / KingMode-style flourish).
- grounding: keep >=1 real file:line.
- confidence: HIGH only when grounding is explicit text.`,
    { label: `adjudicate:${claim.id}`, phase: 'Verify', agentType: 'Explore', schema: VETTED_SCHEMA }),
);

// ===== Stage 4: REPORT -- survivors to MAIN THREAD (which writes UI-DESIGN-SPEC.md) =====
const survivors = vetted.filter(Boolean).filter((c) => c.survives);
const byBinding = survivors.reduce((m, c) => { m[c.binding] = (m[c.binding] || 0) + 1; return m; }, {});
const byDim = survivors.reduce((m, c) => { m[c.dim] = (m[c.dim] || 0) + 1; return m; }, {});
log(`VERIFY: ${survivors.length}/${toVerify.length} claims survived adversarial refute `
  + `(MUST=${byBinding.MUST || 0}, SHOULD=${byBinding.SHOULD || 0}, MAY=${byBinding.MAY || 0})`);

phase('Report');
return {
  counts: {
    cataloguers: catalogues.length,
    rawClaims: rawClaims.length,
    deduped: claims.length,
    verified: toVerify.length,
    deferred: Math.max(0, claims.length - VERIFY_CAP),
    survivors: survivors.length,
    byBinding,
    byDim,
  },
  inventory: catalogues.flatMap((c) => (c.inventory || []).map((i) => ({ ...i, area: c.area }))),
  survivors,
};
