// sm-mvp-converge -- Workflow 2 (fix + ship). Consumes MVP-GAP-REPORT.md findings and drives
// type=code survivors to landed, shippable edits; type=process -> *.proposal.md; type=gate ->
// handed to the MAIN THREAD. Union-find file-disjoint partitions edit in parallel git worktrees;
// 2 isolated refuters per partition; targeted tests; one PR. NEVER main, NEVER force-push, NEVER
// run a Tier-3 soak / real alignment-eval in a subagent. ASCII-only (cp1252). See streamManagerworkflow.md sec 3 (W2).
//
// INVOKE: Workflow({ scriptPath: '.../sm-mvp-converge.js', args: {
//   findings: [<actionable findings from the report>],   // optional; if absent a reader agent parses MVP-GAP-REPORT.md
//   pin: { cycleTip: '70e23e5', ... },                    // denominator pin
//   openPr: false,                                        // DEFAULT false: prepare branch+commit only, NO push/PR (outward-facing => operator-authorized)
//   tag: 'sm-mvp-<date>'                                  // branch suffix
// }})
export const meta = {
  name: 'sm-mvp-converge',
  description: 'Fix half: union-find partition the MVP-GAP-REPORT findings, file-disjoint parallel minimal edits in git worktrees, adversarial refute x2, targeted tests, PR. Never main/force-push. type=process->proposal, type=gate->main thread.',
  phases: [{ title: 'Split' }, { title: 'Fix' }, { title: 'Verify+Ship' }],
};

const PIN = (args && args.pin) || { cycleTip: '70e23e5' };
const ANCHOR = PIN.cycleTip || '70e23e5';
const OPEN_PR = !!(args && args.openPr);
const TAG = (args && args.tag) || 'sm-mvp';

const SAFETY = [
  'FIREWALL (G1): never read/edit **/certPortal/** or C:/Users/SeanHoppe/VS/certPortal/**. A fired deny is surfaced, never worked around.',
  'POLARITY (G2): any corpus/ingest path INCLUDES a row iff project_slug NOT IN {streamManager} AND session_id != BRIDGE_SM_SELF_SESSION_ID, at SQL WHERE. Self-session rows are a FAIL.',
  'ASCII-only (G11): emitted .md/.py pass content.encode("cp1252") with no UnicodeEncodeError. No smart quotes, em-dashes (--), box-drawing, section-sign.',
  'ZERO-CONTAMINATION: introduce no certPortal vocab / JOB-IDs / monitored-role-names into SM source/docs/tests.',
].join('\n');

// HARD GUARDS (checked at edit time inside each fix agent; BLOCK or re-route a partition).
const GUARDS = [
  'G-FROZEN: FROZEN seams = governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py, envelope_kinds.py + bus envelope schemas.',
  '  Bugfix-additive (new OPTIONAL kwarg / enum case / metadata field, NO new caller edge) = permitted.',
  '  A NEW import/call edge into a FROZEN seam = re-route to a #131-style freeze-lift *.proposal.md (do NOT edit). A band/schema reorder = BLOCK.',
  '  (Validation note: the governance_decision envelope agent_role gap is a DELIBERATE freeze deferred to Issue #215 -> freeze-amendment proposal, not an auto-edit.)',
  'G-ENVELOPE: a new bus envelope kind (new enum member in envelope_kinds.py) without same-PR cassette_record.py + soak_driver.py extension in the SAME diff = BLOCK.',
  'G-LOC: git diff ' + ANCHOR + '..HEAD --shortstat -- src tools dashboard. Binding scope = src+tools+dashboard (tests+docs advisory). BLOCK at net >= 2250; WARN 1500<net<=2250; consolidation PASS iff net <= 0.',
  'G-FIREWALL: rg -i "certportal|JOB-[0-9]|<monitored-role-names>" over changed files -> any hit = BLOCK. Any path matching **/certPortal/** = BLOCK + surface. is_corpus_ingest_path without polarity dual-key WHERE = BLOCK.',
  'G-LONGTASK: if a finding verify is a Tier-3 soak or real alignment-eval, reclassify type=gate and hand to main thread. The workflow REFUSES to run it.',
].join('\n');

// ---------- helpers (pure JS; no fs) ----------
function unionFindBySharedFile(codeFindings) {
  // any two findings sharing a file land in the same partition (serial within); disjoint -> parallel.
  const parent = {};
  const find = (x) => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
  const union = (a, b) => { parent[find(a)] = find(b); };
  codeFindings.forEach((f, i) => { parent[i] = i; });
  const fileOwner = {};
  codeFindings.forEach((f, i) => {
    for (const file of (f.files || [])) {
      if (fileOwner[file] === undefined) fileOwner[file] = i;
      else union(i, fileOwner[file]);
    }
  });
  const groups = {};
  codeFindings.forEach((f, i) => {
    const r = find(i);
    (groups[r] = groups[r] || { id: `part-${r}`, findings: [], files: new Set() });
    groups[r].findings.push(f);
    (f.files || []).forEach((x) => groups[r].files.add(x));
  });
  return Object.values(groups).map((g) => ({ id: g.id, findings: g.findings, files: [...g.files] }));
}

function FIX_PROMPT(part) {
  return `${SAFETY}\n\n${GUARDS}\n\n` +
    `You are a minimal-edit fixer working in an ISOLATED git worktree at cycle-tip anchor ${ANCHOR}.\n` +
    `Partition ${part.id}. Findings (type=code) to resolve, confined to files[] + their tests:\n` +
    `${JSON.stringify(part.findings.map((f) => ({ id: f.id, title: f.title, files: f.files, surfaceClass: f.surfaceClass, rootCause: f.rootCause, verifyCmd: f.verifyCmd, binaryPass: f.binaryPass, note: f.note })), null, 1)}\n\n` +
    `Rules: smallest correct edit per finding; touch ONLY files[] (+ their direct tests). Run the HARD GUARDS before each edit:\n` +
    `- If an edit would add a new caller edge into a FROZEN seam, DO NOT edit: set rerouted=true with a freeze-lift proposal stub.\n` +
    `- Keep the partition's net binding LOC minimal; report locDelta.\n` +
    `After edits: run each finding's verifyCmd (targeted pytest -k / ruff check <changed> / mypy / path_d_verify for rl/). ` +
    `ASCII cp1252 round-trip every emitted file.\n` +
    `CRITICAL -- capture your worktree changes: run \`git diff\` (and \`git diff --stat\`) INSIDE your worktree and put the FULL output in the diff field. ` +
    `This is the ONLY way refuters can see your edits (they run in a different tree and CANNOT see your worktree). If diff is empty you did not actually edit -- report that honestly.\n` +
    `Return: { partitionId, editedFiles[], perFinding:[{id, edited|rerouted|blocked, reason}], testsPass, locDelta, guardTrips[], diff }.`;
}

const PARTITION_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['partitionId', 'editedFiles', 'perFinding', 'testsPass', 'locDelta', 'guardTrips', 'diff'],
  properties: {
    partitionId: { type: 'string' },
    editedFiles: { type: 'array', items: { type: 'string' } },
    perFinding: { type: 'array', items: { type: 'object', additionalProperties: true } },
    testsPass: { type: 'boolean' },
    locDelta: { type: 'string' },
    guardTrips: { type: 'array', items: { type: 'string' } },
    diff: { type: 'string' },   // the worktree `git diff` (the fixer's ACTUAL uncommitted edits) -- fed verbatim to refuters
  },
};

const REFUTE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['partitionId', 'verdict', 'note'],
  properties: {
    partitionId: { type: 'string' },
    verdict: { type: 'string', enum: ['SOUND', 'REGRESSION', 'OVERREACH', 'GUARD_VIOLATION'] },
    note: { type: 'string' },
  },
};

async function refuteLoop(part, fixResult) {
  // 2 isolated READ-ONLY refuters review the FIXER'S WORKTREE DIFF (embedded below), NOT git diff anchor..HEAD.
  // The fixer edits an isolated worktree (uncommitted); refuters run in a DIFFERENT tree and CANNOT see it,
  // so `git diff ${ANCHOR}..HEAD` shows committed main (POC-fleet history), NOT the fix -> false REGRESSION.
  // Unanimous SOUND required to ship.
  const DIFF = (fixResult && fixResult.diff) || '(fixer returned NO diff -- treat as: no edit applied)';
  const summaryNoDiff = JSON.stringify({ ...fixResult, diff: undefined });
  const reviewMandate = (who, peer) =>
    `${SAFETY}\n\nRefuter ${who} (READ-ONLY${peer ? `, ISOLATED from ${peer}` : ''}) for partition ${part.id}. ` +
    `Review ONLY the worktree diff below -- it is the fixer's ACTUAL uncommitted edits in its private worktree. ` +
    `Do NOT run \`git diff ${ANCHOR}..HEAD\` or inspect the live working tree: that shows committed main (POC-fleet history), NOT this fix, and will mislead you into a false REGRESSION. ` +
    `Judge ONLY whether the diff below correctly resolves the partition findings.\n` +
    `Fix summary (sans diff): ${summaryNoDiff}\n\n===WORKTREE DIFF (the only ground truth)===\n${DIFF}\n===END DIFF===\n\n` +
    `Hunt: does the diff actually resolve each finding (REGRESSION if empty/absent/wrong); scope-overreach beyond files[] (OVERREACH); ` +
    `a HARD-GUARD violation (new FROZEN caller edge / envelope-without-cassette / firewall or polarity leak / certPortal vocab / non-cp1252 char / LOC blow-out) (GUARD_VIOLATION). ` +
    `SOUND only if the diff resolves the findings within scope and trips no guard. Return SOUND | REGRESSION | OVERREACH | GUARD_VIOLATION + note.`;
  const refs = (await parallel([
    () => agent(reviewMandate('A', null), { label: `refute:${part.id}:A`, phase: 'Fix', agentType: 'Explore', schema: REFUTE_SCHEMA }),
    () => agent(reviewMandate('B', 'A'), { label: `refute:${part.id}:B`, phase: 'Fix', agentType: 'Explore', schema: REFUTE_SCHEMA }),
  ])).filter(Boolean);
  const unanimous = refs.length === 2 && refs.every((r) => r.verdict === 'SOUND') && fixResult.testsPass;
  return { ...fixResult, refuters: refs, unanimous };
}

function emitProposalMd(f) {
  // type=process: a proposal artefact, zero code edit. Returned for a writer agent to materialize.
  return {
    id: f.id,
    path: `proposals/${f.id}.proposal.md`,
    body: `# Proposal ${f.id}\n\n- type: process\n- scope: ${f.scope}\n- invariant: ${f.invariantId}\n- root cause: ${f.rootCause}\n- evidence: ${(f.evidencePaths || []).join('; ')}\n- recommended action: <operator/process change; no code edit>\n`,
  };
}

// ---------- Stage: Split ----------
phase('Split');
let findings = (args && args.findings) || [];
if (!findings.length) {
  // fallback: a reader agent parses the report (scripts have no fs access).
  const READER_SCHEMA = { type: 'object', additionalProperties: false, required: ['findings'],
    properties: { findings: { type: 'array', items: { type: 'object', additionalProperties: true } } } };
  const r = await agent(`${SAFETY}\n\nRead MVP-GAP-REPORT.md section 2 (actionable findings). For each "### FINDING <id> [type=..] [scope=..] [surface=..]" ` +
    `block, extract {id, type, scope, surfaceClass, title, invariantId, rootCause, evidencePaths[], files[], verifyCmd, binaryPass, note}. ` +
    `SKIP section 8 merged duplicates. Return findings[].`,
    { label: 'read-report', phase: 'Split', agentType: 'Explore', schema: READER_SCHEMA });
  findings = (r && r.findings) || [];
}
const code = findings.filter((f) => f.type === 'code');
const proc = findings.filter((f) => f.type === 'process');
const gate = findings.filter((f) => f.type === 'gate');
const partitions = unionFindBySharedFile(code);
log(`SPLIT: ${findings.length} findings -> code ${code.length} (${partitions.length} file-disjoint partitions), process ${proc.length}, gate ${gate.length}`);

// ---------- Stage: Fix (parallel, worktree-isolated) ----------
phase('Fix');
const shipped = await parallel(partitions.map((part) => () =>
  agent(FIX_PROMPT(part), { label: `fix:${part.id}`, phase: 'Fix', isolation: 'worktree', agentType: 'general-purpose', schema: PARTITION_SCHEMA })
    .then((r) => (r ? refuteLoop(part, r) : null))
));
const proposals = proc.map(emitProposalMd);

// ---------- Stage: Verify + Ship ----------
phase('Verify+Ship');
const shippable = shipped.filter(Boolean).filter((p) => p.unanimous);
const blocked = shipped.filter(Boolean).filter((p) => !p.unanimous);

// PR step is OUTWARD-FACING: only when args.openPr === true (operator-authorized). Else prepare-only.
let shipResult = { openPr: OPEN_PR, branch: `fix/${TAG}`, prepared: shippable.map((p) => p.partitionId) };
if (OPEN_PR && shippable.length) {
  const SHIP_SCHEMA = { type: 'object', additionalProperties: false, required: ['branch', 'committed', 'prUrl'],
    properties: { branch: { type: 'string' }, committed: { type: 'boolean' }, prUrl: { type: 'string' } } };
  // CRITICAL: the fixers edited ISOLATED worktrees the ship agent CANNOT see (same worktree-blindness
  // as the refuter bug). Hand the ship agent each partition's captured `diff` and have it `git apply`
  // them onto the fresh branch -- never expect it to discover the worktree edits itself.
  const shipPayload = shippable.map((p) => ({ id: p.partitionId, editedFiles: p.editedFiles, diff: p.diff }));
  shipResult = await agent(`${SAFETY}\n\nShip agent. The shippable partitions were edited in ISOLATED git worktrees you CANNOT see; ` +
    `their captured worktree diffs are provided below. Create a NEW branch fix/${TAG} off main ` +
    `(NEVER commit to main, NEVER force-push, NEVER --no-verify). For each partition, reconstruct its edits by ` +
    `\`git apply --whitespace=nowarn\` of its diff (the partitions are file-disjoint, so order does not matter; ` +
    `a partition whose diff is empty/absent must be SKIPPED, not re-implemented). Stage ONLY the files named in each ` +
    `partition's editedFiles[] (explicit paths, never \`git add -A\`). Re-run the G11 cp1252 gate, ruff, mypy, and the ` +
    `targeted tests on the assembled tree. One commit citing finding IDs, ending ` +
    `"Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>". Push + open ONE PR (gh pr create) targeting main.\n` +
    `Shippable partitions (id, editedFiles, diff):\n${JSON.stringify(shipPayload)}\n\n` +
    `Return { branch, committed, prUrl }.`,
    { label: 'ship', phase: 'Verify+Ship', agentType: 'general-purpose', schema: SHIP_SCHEMA });
}

return {
  anchor: ANCHOR,
  shippablePartitions: shippable.map((p) => ({ id: p.partitionId, editedFiles: p.editedFiles, locDelta: p.locDelta })),
  blockedPartitions: blocked.map((p) => ({ id: p.partitionId, guardTrips: p.guardTrips, refuters: p.refuters })),
  proposals,                                  // type=process artefacts (writer agent materializes, or main thread writes)
  handToMainThread: gate.map((g) => ({ id: g.id, cmd: g.verifyCmd, pass: g.binaryPass,
    runVia: 'run_in_background + ScheduleWakeup', why: 'Tier-3 soak / real alignment-eval / FROZEN freeze-lift' })),
  ship: shipResult,
  note: OPEN_PR ? 'PR opened (operator-authorized).' : 'DRY-RUN: branch/commit prepared in worktrees, NO push/PR. Re-invoke with args.openPr=true to ship.',
};
