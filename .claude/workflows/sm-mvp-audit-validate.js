// sm-mvp-audit-validate -- independent adversarial validation of MVP-GAP-REPORT.md.
// NOT a re-run of the audit; a curated second-opinion pass over the residual-risk findings the
// main thread did not hand-verify: FROZEN surfaceClass correctness (a mis-tag misroutes converge's
// G-FROZEN guard), F6/F7 cluster inflation (template-multiplication), type=code-vs-process, and
// gate-type evidence-only correctness. Read-only Explore agents on HEAD. ASCII-only.
export const meta = {
  name: 'sm-mvp-audit-validate',
  description: 'Independent adversarial validation of curated high-risk MVP-GAP-REPORT.md findings (FROZEN-tag, cluster-inflation, type, gate). Read-only.',
  phases: [{ title: 'Validate' }, { title: 'Cluster-critic' }],
};

const HEAD = 'd8ed70f';
const SAFETY = [
  'READ-ONLY. Read/Glob/Grep/Bash(read-only,<=90s). Never Edit/Write.',
  'FIREWALL: never read **/certPortal/** ; textual SM refs to the monitor target are fine.',
  'POLARITY: corpus reads exclude SM-self at SQL WHERE. ASCII-only output.',
  'You are adversarial: default to MISTAGGED/OVERSTATED/REFUTED when the report over-claims.',
].join('\n');

const REPORT = 'MVP-GAP-REPORT.md';
const FROZEN_SEAMS = 'governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py, envelope_kinds.py (+ bus envelope schemas). rl/** is EXPERIMENTAL, docs are n/a, NOT FROZEN.';

// Curated residual-risk findings (main thread already hand-verified the F8 polarity cluster + hygiene).
const TARGETS = [
  { id: 'F4-cap-clip-falsification-measurement-artefact-5', q: 'type=code surfaceClass=FROZEN. Does the fix touch a FROZEN seam, or is it a measurement/doc artefact (then surfaceClass mis-tagged)?' },
  { id: 'F6-adrObs-003', q: 'type=code surfaceClass=FROZEN on a stale-ADR/memory finding. A doc edit is NOT FROZEN gov surface -- is surfaceClass mis-tagged (should be n/a)? Is type=code right or should it be process?' },
  { id: 'F6-versionStatus-001', q: 'type=code scope=v10-rl. Is this a real stale-doc gap on HEAD, and is type=code (mechanical edit) correct vs process?' },
  { id: 'F7-envelope-agent-role-binding-0001', q: 'surfaceClass=FROZEN. Confirm it actually touches a FROZEN seam. Is the agent-role-binding gap real on HEAD or speculative?' },
  { id: 'F7-cassette-agent-role-binding-probe-0003', q: 'surfaceClass=FROZEN. Real on HEAD? Distinct from F7-envelope-agent-role-binding-0001 or the same gap re-counted?' },
  { id: 'F7-extract-gov-jsonl-agent-role-0002', q: 'surfaceClass=FROZEN. tools/extract_gov_to_jsonl.py is a tool, not a FROZEN gov seam -- mis-tagged? Real gap?' },
  { id: 'F7-governance-decision-agent-role-missing-0005', q: 'surfaceClass=FROZEN. Real on HEAD? Distinct from the other F7 agent-role findings or cluster-inflation?' },
  { id: 'F7-extract-gov-agent-role-missing-0006', q: 'surfaceClass=EXPERIMENTAL. Distinct from F7-extract-gov-jsonl-agent-role-0002 (same file family)? Or duplicate?' },
  { id: 'F8-corpus-schema-missing-project-slug', q: 'surfaceClass=FROZEN on rl/schema.sql. rl/** is EXPERIMENTAL not FROZEN gov surface -- mis-tagged? (The underlying gap IS real -- main thread confirmed no project_slug column; question is ONLY the surfaceClass + whether a schema change is additive-safe.)' },
  { id: 'F9-v1.9-L2L3-budget-violation-8', q: 'type=gate. Confirm it cites EXISTING reports only (no re-run) and the binaryPass needs a main-thread soak/eval. Evidence resolves on HEAD?' },
  { id: 'F9-v2.2-p95-regression-1', q: 'type=gate. Evidence-only (existing soak reports)? Correctly type=gate not code? Numbers match the cited report?' },
  { id: 'F10-cli-pool-size-default-zero', q: 'type=code. Confirm the --cli-pool-size default-0 cold-start war-story is real on HEAD (cite the default value + file:line).' },
];

phase('Validate');
const VSCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'verdict', 'surfaceClassCorrect', 'typeCorrect', 'evidenceResolves', 'note'],
  properties: {
    id: { type: 'string' },
    verdict: { type: 'string', enum: ['CONFIRM', 'OVERSTATED', 'MISTAGGED', 'DUPLICATE', 'REFUTED'] },
    surfaceClassCorrect: { type: 'boolean' },
    surfaceClassShouldBe: { type: 'string' },
    typeCorrect: { type: 'boolean' },
    evidenceResolves: { type: 'boolean' },
    note: { type: 'string' },
  },
};

const verdicts = (await parallel(TARGETS.map((t) => () =>
  agent(`${SAFETY}

Validate finding ${t.id} from ${REPORT} (grep its "### FINDING ${t.id}" block for the claim, files, evidence, surfaceClass, type, verify cmd).
ADR-18 FROZEN seams = ${FROZEN_SEAMS}
Specific question: ${t.q}
Open the cited files on HEAD ${HEAD}. Return:
- verdict: CONFIRM (finding+tags sound) | OVERSTATED | MISTAGGED (surfaceClass/type wrong, finding may still be real) | DUPLICATE (same gap as a sibling) | REFUTED (not real on HEAD).
- surfaceClassCorrect + surfaceClassShouldBe; typeCorrect; evidenceResolves; one-line note.`,
    { label: `val:${t.id}`, phase: 'Validate', agentType: 'Explore', schema: VSCHEMA })
))).filter(Boolean);

phase('Cluster-critic');
const CSCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['f6_distinct_count', 'f7_distinct_count', 'inflation_note', 'mistag_systemic'],
  properties: {
    f6_distinct_count: { type: 'string' },
    f7_distinct_count: { type: 'string' },
    inflation_note: { type: 'string' },
    mistag_systemic: { type: 'string' },
  },
};
const critic = await agent(`${SAFETY}

Cluster critic over ${REPORT}. The report has a large F6 (stale-memory, ~12 findings) and F7 (cross-PR-seam / agent-role-binding, ~7 findings) cluster.
Grep all "### FINDING F6-" and "### FINDING F7-" blocks. Judge: how many are GENUINELY DISTINCT root causes vs the same gap re-counted across sibling files (template-multiplication)?
Also: is FROZEN surfaceClass being systematically over-applied to non-FROZEN (rl/**, tools/**, docs) files?
Return distinct-count estimates + an inflation note + a systemic-mistag note.`,
  { label: 'cluster-critic', phase: 'Cluster-critic', agentType: 'Explore', schema: CSCHEMA });

const mistagged = verdicts.filter((v) => !v.surfaceClassCorrect);
const refuted = verdicts.filter((v) => v.verdict === 'REFUTED');
const dupes = verdicts.filter((v) => v.verdict === 'DUPLICATE');
return {
  validated: verdicts.length,
  confirmed: verdicts.filter((v) => v.verdict === 'CONFIRM').length,
  mistaggedSurfaceClass: mistagged.map((v) => ({ id: v.id, shouldBe: v.surfaceClassShouldBe })),
  refuted: refuted.map((v) => v.id),
  duplicates: dupes.map((v) => v.id),
  perFinding: verdicts,
  clusterCritic: critic,
};
