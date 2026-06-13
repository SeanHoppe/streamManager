// sm-ux-propose -- Outside-the-box proposal-mint workflow (directive #5 + #6).
// Rosetta-Stone of Claude-ResearchFixWorkflow.md /report-fixes PROPOSAL half (process findings never
// touch code -- each becomes a written *.proposal.md). Recast for NEW-FUNCTIONALITY ideation:
//   bold KingMode-persona ideation -> adversarial feasibility/firewall/polarity/MUST refute -> per-idea
//   proposal brief the main thread writes to reports/proposals/.
//
// Covers:
//   #5 new functionality + operator comforts -- a COMFORTS angle that explicitly includes the named
//      example "cleanup stale sessions" plus other laptop-operator quality-of-life.
//   #6 think outside the box -- the ideation stage is told to be BOLD and NOT to apologize for strange
//      ideas. "Make it happen" means AUTHOR the proposal end-to-end -- it does NOT mean bypass governance:
//      the refute stage still holds the firewall / polarity / ADR-18 MUST floor. A bold idea that crosses
//      a MUST is CONSTRAINED (reshaped to comply), never silently killed; only the infeasible is KILLED.
//
// NEVER edits/builds/soaks. Output = structured proposal briefs; the main thread writes the *.proposal.md
// files (this workflow does not write fs). ASCII-only (cp1252). ARGS-DRIVEN.
//   args: { audit, targetDir, ideaCount, seedIdeas[] }
//     audit      = the sm-ux-audit result (survivors/gaps/inventory) -- grounds proposals in real findings.
//     seedIdeas  = operator-supplied idea seeds to force into the panel (optional).
export const meta = {
  name: 'sm-ux-propose',
  description: 'Outside-the-box new-functionality + operator-comfort proposal mint. KingMode-persona bold ideation (incl. stale-session cleanup + wild ideas, no apology) -> adversarial feasibility/firewall/polarity/ADR-18 MUST refute (bold-but-non-compliant ideas are CONSTRAINED not killed) -> per-idea proposal brief for the main thread to write to reports/proposals/. Never edits/builds/soaks.',
  phases: [{ title: 'Ideate' }, { title: 'Refute' }, { title: 'Propose' }],
};

const KINGMODE = [
  'PERSONA: Senior Frontend Architect & Avant-Garde UI Designer + systems thinker (docs/KingModePrompt.txt).',
  'Anti-generic: reject template/obvious features. Bespoke, asymmetric, distinctive. Maximum depth of reasoning.',
  'BOLD MANDATE (directive #6): think outside the box. Strange / crazy / ambitious ideas are WELCOME. Do NOT',
  '  apologize for an idea and do NOT pre-water it down -- propose it at full ambition. The refute stage is',
  '  where compliance gets enforced; your job here is range and originality, not timidity.',
].join('\n');

const SAFETY = [
  'READ-ONLY here. Read/Glob/Grep/Bash(read-only, <=60s). NEVER Edit/Write/commit/build/install/soak.',
  '  (The main thread writes the proposal files; you only return structured briefs.)',
  'FIREWALL (G1): never read/glob/grep **/certPortal/**. A proposal MUST NOT add new certPortal coupling',
  '  beyond already-designed (learn-mode source registry, project_context, agent_profiles).',
  'ZERO-CONTAMINATION (G11): a proposal MUST stay domain-agnostic -- NO monitored-project vocab/JOB-IDs/roles',
  '  baked into SM. Governed-target identity is configuration rendered from data, never hard-coded vocabulary.',
  '  ASCII-only output (cp1252): no smart quotes, no em-dashes (write --), no box-drawing.',
  'POLARITY (G2): no proposal may make SM monitor/govern its own session. SM monitors NON-SM sessions only',
  '  (project_slug NOT IN {streamManager} AND session_id != self). A "cleanup stale sessions" comfort must',
  '  exclude the SM-self session from any sweep.',
  'ADR-18 MUST FLOOR: the binding UI MUSTs (3-frame presence, escalation-only foreground, paired label+color',
  '  badges -- color alone is never a signal, absolute HITL gate, domain-agnostic, a11y axe gate, latency',
  '  budget, non-goals = no IDE/multiplexer/multi-tenant) are inviolable. A proposal bends SHOULD/MAY, never a MUST.',
  'SCOPE: proposals target the EXPERIMENTAL ui-next spike + SM backend as PROPOSALS only. They do not authorize',
  '  edits to FROZEN surfaces (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py);',
  '  a proposal touching those names must state the ADR amendment it would require first.',
  'NEW BUS ENVELOPE RULE: if a proposal introduces a new bus envelope kind, it MUST note that shipping requires',
  '  same-PR cassette_record.py + soak_driver.py coverage (feedback_cassette_must_cover_new_envelopes).',
].join('\n');

const IN = (args && typeof args === 'object') ? args : {};
const AUDIT = IN.audit && typeof IN.audit === 'object' ? IN.audit : null;
const TARGET = IN.targetDir || 'dashboard/ui-next/';
const SEEDS = Array.isArray(IN.seedIdeas) ? IN.seedIdeas.slice(0, 20) : [];
const N_IDEAS = Math.max(2, Math.min(6, Number(IN.ideaCount) || 5));

// Distilled audit context (kept small so it threads into prompts cleanly).
const AUDIT_BLOCK = AUDIT
  ? `GROUNDING -- sm-ux-audit findings (anchor proposals in these real survivors):\n`
    + `friction/enhance: ${JSON.stringify((AUDIT.survivors || []).filter((s) => s.disposition === 'FRICTION' || s.disposition === 'ENHANCE').map((s) => ({ surface: s.surface, claim: s.claim, g: s.grounding })).slice(0, 40))}\n`
    + `soak gaps: ${JSON.stringify((AUDIT.soakGaps || []).map((s) => ({ claim: s.claim, g: s.grounding })).slice(0, 20))}\n`
    + `deprecate (do NOT re-propose dead surfaces): ${JSON.stringify((AUDIT.deprecate || []).map((s) => s.surface).slice(0, 30))}\n`
  : `(No audit result supplied -- ideate from INTENT.md / REQUIREMENTS.md / UI-DESIGN-SPEC.md / MEMORY.md directly. Recommend running sm-ux-audit first so proposals are grounded in real findings.)\n`;

// ---- Ideation angles -- each generator owns a distinct lane so coverage is by-kind ----
const ANGLES = [
  { id: 'COMFORTS', lane: 'operator comforts / quality-of-life',
    hint: 'Laptop-operator quality-of-life that removes toil. The NAMED example (#5): "cleanup stale sessions" -- a comfort that detects sessions whose JSONL has gone quiet / process exited / cwd vanished and offers a one-click (or auto, opt-in) sweep, EXCLUDING the SM-self session (polarity). Also: session pinning, quick-filter presets, keyboard-only operation, a "calm/away" mode, restore-last-layout, bulk-dismiss aged HITL rows. Concrete, shippable, low-risk.' },
  { id: 'MONITOR', lane: 'monitor-first superpowers',
    hint: 'Make the monitor-first UI genuinely magical for watching many concurrent governed sessions: at-a-glance health sparklines per session, an escalation timeline, a "what changed since I looked away" digest, ambient signaling that respects the escalation-only-foreground MUST, diff-of-decisions, a session heat map. Glance-readability is the prize.' },
  { id: 'SOAK', lane: 'soak / non-SM-session validation as a product surface',
    hint: 'Turn the soak-for-non-SM-sessions path (directive #2 / #r1) into something first-class: a UI to pick a live non-SM Claude session as a soak target (polarity-guarded, refuse SM-self + firewalled cwd), live soak progress in the dashboard, a "shadow soak" lane, replay-a-recorded-session, surfacing the synthetic-vs-live-session coverage gap the audit found. Anchor in soak_driver.py + ADR-17 tiers.' },
  { id: 'WILDCARD', lane: 'strange / ambitious / outside-the-box',
    hint: 'The crazy lane (#6). Do NOT apologize. Examples to spark, go further: a governance "time machine" scrubber that replays the decision stream; an operator co-pilot chip that proposes the next HITL action with a confidence the operator can one-tap accept; a spatial/canvas session map; voice or sound-design for escalation; a "governance replay diff" between two policy versions; an LLM-narrated session summary on the calm screen. Must still survive the firewall/polarity/MUST refute -- aim high, the refuter will constrain.' },
  { id: 'BACKEND', lane: 'backend / API capability that unlocks UI value',
    hint: 'Backend or API capabilities that would unlock operator value: a /api/sessions/stale endpoint feeding the cleanup comfort; a session lifecycle event stream; server-side digest of "since last seen"; a soak-target registry. Note FROZEN-surface boundaries and the new-envelope cassette rule where relevant.' },
];

// ---- Schemas ----
const IDEA_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['lane', 'ideas'],
  properties: {
    lane: { type: 'string' },
    ideas: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['id', 'title', 'problem', 'idea', 'operatorValue', 'surfaces'],
      properties: {
        id: { type: 'string' },
        title: { type: 'string' },
        problem: { type: 'string' }, // the operator pain it removes
        idea: { type: 'string' }, // the proposal at full ambition (no pre-watering)
        operatorValue: { type: 'string' },
        surfaces: { type: 'array', items: { type: 'string' } }, // files/endpoints it would touch or add
        boldness: { type: 'string', enum: ['SAFE', 'STRETCH', 'WILD'] },
        grounding: { type: 'array', items: { type: 'string' } }, // file:line anchors where relevant
      },
    } },
  },
};

const REFUTE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ideaId', 'verdict', 'checks', 'reasoning'],
  properties: {
    ideaId: { type: 'string' },
    verdict: { type: 'string', enum: ['SHIP-PROPOSAL', 'CONSTRAIN', 'KILL'] },
    checks: { type: 'object', additionalProperties: false,
      required: ['firewall', 'polarity', 'mustFloor', 'feasibility', 'valueReal'],
      properties: {
        firewall: { type: 'string', enum: ['PASS', 'FAIL'] },
        polarity: { type: 'string', enum: ['PASS', 'FAIL'] },
        mustFloor: { type: 'string', enum: ['PASS', 'BENDS-SHOULD', 'VIOLATES-MUST'] },
        feasibility: { type: 'string', enum: ['FEASIBLE', 'HARD', 'INFEASIBLE'] },
        valueReal: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
      } },
    constraint: { type: 'string' }, // if CONSTRAIN: exactly how to reshape it to comply (never silently drop)
    reasoning: { type: 'string' },
  },
};

const PROPOSAL_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ideaId', 'slug', 'title', 'problem', 'proposal', 'operatorValue', 'feasibility', 'compliance', 'effort'],
  properties: {
    ideaId: { type: 'string' },
    slug: { type: 'string' }, // kebab filename stem for reports/proposals/<date>-<slug>.proposal.md
    title: { type: 'string' },
    problem: { type: 'string' },
    proposal: { type: 'string' }, // the concrete change (constrained to comply if the refuter said so)
    operatorValue: { type: 'string' },
    surfaces: { type: 'array', items: { type: 'string' } },
    feasibility: { type: 'string' },
    compliance: { type: 'object', additionalProperties: false,
      required: ['firewall', 'polarity', 'mustFloor', 'frozenSurfaceNote', 'newEnvelopeNote'],
      properties: {
        firewall: { type: 'string' },
        polarity: { type: 'string' },
        mustFloor: { type: 'string' },
        frozenSurfaceNote: { type: 'string' }, // any FROZEN surface it would need + the ADR amendment
        newEnvelopeNote: { type: 'string' }, // cassette/soak coverage if a new envelope kind is added
      } },
    boldness: { type: 'string', enum: ['SAFE', 'STRETCH', 'WILD'] },
    effort: { type: 'string', enum: ['S', 'M', 'L', 'XL'] },
    grounding: { type: 'array', items: { type: 'string' } },
  },
};

// ===== Stage 1: IDEATE -- one bold generator per angle (barrier; refuters need the full set) =====
phase('Ideate');
const SEED_BLOCK = SEEDS.length ? `\nOperator-forced seed ideas (carry them into the panel, refine, do not drop): ${JSON.stringify(SEEDS)}\n` : '';
const ideaSets = (await parallel(ANGLES.slice(0, Math.max(4, N_IDEAS)).map((a) => () =>
  agent(`${KINGMODE}

${SAFETY}

${AUDIT_BLOCK}${SEED_BLOCK}
Ideation lane "${a.lane}" (${a.id}). ${a.hint}
Produce ${a.id === 'WILDCARD' ? '3 to 5' : '2 to 4'} distinct ideas at FULL ambition. For each: title, the operator
problem it removes, the idea (do not pre-water it -- the refuter enforces compliance later), operatorValue,
the surfaces (files under ${TARGET} / endpoints / backend) it would touch or add, boldness SAFE|STRETCH|WILD,
and grounding file:line where the pain or hook is real. ids unique e.g. "${a.id}-<n>".`,
    { label: `ideate:${a.id}`, phase: 'Ideate', agentType: 'Explore', schema: IDEA_SCHEMA })
))).filter(Boolean).flatMap((r) => (r.ideas || []).map((i) => ({ ...i, lane: r.lane })));
log(`IDEATE: ${ideaSets.length} ideas across ${ANGLES.length} lanes `
  + `(WILD=${ideaSets.filter((i) => i.boldness === 'WILD').length}, STRETCH=${ideaSets.filter((i) => i.boldness === 'STRETCH').length}, SAFE=${ideaSets.filter((i) => i.boldness === 'SAFE').length})`);

// ===== Stage 2+3: REFUTE -> PROPOSE -- pipeline per idea (no barrier) =====
const IDEA_CAP = 40;
const toProcess = ideaSets.slice(0, IDEA_CAP);
if (ideaSets.length > IDEA_CAP) log(`IDEA cap: ${ideaSets.length} ideas; processing first ${IDEA_CAP}, ${ideaSets.length - IDEA_CAP} DEFERRED (logged)`);

phase('Refute');
const processed = await pipeline(
  toProcess,
  // Stage A: adversarial feasibility + compliance gate. Bold-but-non-compliant -> CONSTRAIN, not silent KILL.
  (idea) => agent(`${SAFETY}

Adversarial gate for idea ${idea.id} [boldness=${idea.boldness}]. You are SKEPTICAL but FAIR.
Title: ${idea.title}
Idea: ${idea.idea}
Surfaces: ${JSON.stringify(idea.surfaces)}
Operator value claimed: ${idea.operatorValue}
Run every check and open files where needed:
- firewall: does it add NEW certPortal/monitored-project coupling or vocab? PASS/FAIL.
- polarity: could it make SM monitor/govern its own session, or sweep SM-self? PASS/FAIL.
- mustFloor: does it cross an ADR-18 UI MUST? PASS | BENDS-SHOULD | VIOLATES-MUST.
- feasibility: buildable on the existing API/SSE contract + ui-next stack? FEASIBLE | HARD | INFEASIBLE.
- valueReal: real operator value for a laptop monitor-first user? HIGH | MEDIUM | LOW.
VERDICT: SHIP-PROPOSAL (clean) | CONSTRAIN (reshape to comply -- give the exact constraint, NEVER drop a fixable
idea) | KILL (only firewall FAIL that cannot be designed out, or INFEASIBLE, or LOW value with no salvage).
A WILD idea is NOT killed for being wild -- only for a hard violation. Give reasoning.`,
    { label: `refute:${idea.id}`, phase: 'Refute', agentType: 'Explore', schema: REFUTE_SCHEMA }),
  // Stage B: write the proposal brief for survivors (SHIP-PROPOSAL or CONSTRAIN).
  (refute, idea) => {
    if (!refute || refute.verdict === 'KILL') return Promise.resolve({ killed: true, idea, refute });
    return agent(`${KINGMODE}

${SAFETY}

Author the PROPOSAL BRIEF for idea ${idea.id}. The adversarial gate returned: ${JSON.stringify(refute)}
${refute.verdict === 'CONSTRAIN' ? 'You MUST fold in the refuter constraint -- the proposal as written must comply.' : ''}
Original idea: ${idea.idea} | problem: ${idea.problem} | value: ${idea.operatorValue} | surfaces: ${JSON.stringify(idea.surfaces)}
Produce a self-contained brief: slug (kebab), title, problem, proposal (the concrete change -- constrained to comply),
operatorValue, surfaces, feasibility, compliance{firewall, polarity, mustFloor, frozenSurfaceNote (any FROZEN surface
+ the ADR amendment it needs), newEnvelopeNote (cassette/soak coverage if a new envelope kind is added)}, boldness,
effort S|M|L|XL, grounding file:line. This becomes reports/proposals/<date>-<slug>.proposal.md.`,
      { label: `propose:${idea.id}`, phase: 'Propose', agentType: 'Explore', schema: PROPOSAL_SCHEMA })
      .then((p) => ({ killed: false, idea, refute, proposal: p }));
  },
);

// ===== Aggregate =====
phase('Propose');
const results = processed.filter(Boolean);
const proposals = results.filter((r) => !r.killed && r.proposal).map((r) => ({ ...r.proposal, verdict: r.refute.verdict }));
const killed = results.filter((r) => r.killed).map((r) => ({ id: r.idea.id, title: r.idea.title, reason: r.refute ? r.refute.reasoning : 'no verdict' }));
const byBold = proposals.reduce((m, p) => { m[p.boldness] = (m[p.boldness] || 0) + 1; return m; }, {});
log(`PROPOSE: ${proposals.length} proposal briefs (WILD=${byBold.WILD || 0}, STRETCH=${byBold.STRETCH || 0}, SAFE=${byBold.SAFE || 0}); ${killed.length} killed`);

return {
  scope: 'EXPERIMENTAL-spike-proposals',
  counts: { ideas: ideaSets.length, processed: toProcess.length, proposals: proposals.length, killed: killed.length, byBoldness: byBold },
  proposals, // main thread writes each to reports/proposals/<date>-<slug>.proposal.md
  killed, // logged, never silently dropped
  mainThreadWrite: {
    note: 'Write each proposal to reports/proposals/<date>-<slug>.proposal.md (ASCII-only). The cleanup-stale-sessions '
      + 'comfort (#5) and any backend/new-envelope proposal must carry its compliance.frozenSurfaceNote + newEnvelopeNote forward.',
    dir: 'reports/proposals/',
  },
};
