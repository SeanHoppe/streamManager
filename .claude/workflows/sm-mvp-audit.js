// sm-mvp-audit -- Workflow 1 of the streamManagerworkflow.md suite (OQ-D Option B: wired first).
// Read-only SM MVP-gap + governance-discipline audit. Fan-out cataloguers -> blind loop-until-dry
// finders -> isolated adversarial refuters + adjudicator -> survivors returned to MAIN THREAD,
// which writes MVP-GAP-REPORT.md (the parseable input contract for /sm-mvp-converge).
// NEVER runs a soak / alignment-eval; READS existing reports as frozen evidence. ASCII-only (cp1252).
export const meta = {
  name: 'sm-mvp-audit',
  description: 'Read-only SM MVP-gap + governance-discipline audit; returns survivor findings for MVP-GAP-REPORT.md. Never runs a soak/alignment-eval; reads existing reports as frozen evidence.',
  phases: [{ title: 'Catalog' }, { title: 'Find' }, { title: 'Verify' }, { title: 'Report' }],
};

const ANCHOR = '70e23e5'; // PIN: cycle-tip anchor (v2.8 P0, #211). Cannot rebaseline.

const SAFETY = [
  'READ-ONLY. Read/Glob/Grep/Bash(read-only, <=90s) only. NEVER Edit/Write/commit.',
  'FIREWALL (G1): never read/glob/grep **/certPortal/** or C:/Users/SeanHoppe/VS/certPortal/**.',
  '  A fired deny is surfaced, never worked around. SM source that textually references certPortal is fine.',
  'POLARITY (G2): any corpus/ingest/replay read INCLUDES a row iff project_slug NOT IN {streamManager}',
  '  AND session_id != BRIDGE_SM_SELF_SESSION_ID, enforced at SQL WHERE. Self-session rows are a FAIL.',
  'LONG-TASK (G7): NEVER run a Tier-3 soak or real `claude -p` alignment-eval. Read existing reports only.',
  'ZERO-CONTAMINATION (G11): no certPortal vocab/JOB-IDs/roles introduced. ASCII-only output (cp1252):',
  '  no smart quotes, no em-dashes (write --), no box-drawing, no section-sign.',
  'Output STRUCTURED findings only (the schema). No prose preamble.',
].join('\n');

const TOOLCHAIN = [
  'Cite exactly ONE runnable verify command + its binary pass. Verified library:',
  '- fast-test:    python -m pytest -m "not slow and not alignment_eval" -q   (exit 0)',
  '- scoped-test:  python -m pytest tests/<f>.py -k <expr> -q                 (exit 0)',
  '- ledger-drift: python -m pytest tests/test_dormant_ledger_consistency.py -q (exit 0)',
  '- ruff:         python -m ruff check src tests tools dashboard rl          (exit 0)',
  '- mypy:         python -m mypy                                             (exit 0)',
  '- loc-delta:    git diff 70e23e5..HEAD --shortstat -- src tests tools dashboard  (src+tools+dashboard net <=1500 soft / 2250 BLOCK)',
  '- ship-gate:    python -m tools.ship_gate_runner all                       (exit 0; excludes soak S2 + align S4)',
  '- rl-validate:  python -m rl.cli.validate --candidate <c> --baseline <b> --db rl_episodes.db  (exit 0, advisory/EXPERIMENTAL)',
  '- rl-criteria:  python -m rl.cli.check_criteria --shadow-db rl_shadow.db --manifests rl_proposals/  (exit 0 = all 6 PASS)',
  '- path-d-verify: python tools/path_d_verify.py --json                      (exit 0 lineage clean / exit 2 drift)',
  'NEVER cite a Tier-3 soak or `alignment_eval ... --execute` as a verifyCmd -- those are main-thread',
  'gate items: mark such a finding type=gate with the composed argv + binary criterion instead.',
].join('\n');

// ---- CORPUS map (13 read-only cataloguer areas) -- section 3, W1 ----
const CORPUS = [
  { id: 'C1', glob: 'docs/v*-task-plan.md, docs/v*-next-steps.md, docs/v*-backlog.md, docs/v*-scope.md, docs/2026-*-task-list.md',
    lenses: ['held-chain-deadlock', 'stale-memory', 'intent-reality-gap', 'cross-PR-seam-gap', 'scaffolding-debt'] },
  { id: 'C2', glob: 'docs/adr/ADR-*.md',
    lenses: ['surface-freeze-violation', 'dormant-lever', 'stale-memory', 'intent-reality-gap'] },
  { id: 'C3', glob: 'docs/prompts/**/*.md',
    lenses: ['scaffolding-debt', 'subagent-escape-hatch', 'long-task-misplacement'] },
  { id: 'C4', glob: 'docs/seed-*.md, docs/v2.5.1-*.md, docs/v1.3-*-audit.md, docs/soak-trigger-matrix.md',
    lenses: ['alignment-floor-erosion', 'held-chain-deadlock', 'stale-memory'] },
  { id: 'C5', glob: 'docs/jobs/MASTER.md, docs/jobs/issue-*.md, docs/v10-mvp-status.md, docs/v10-*.md',
    lenses: ['held-chain-deadlock', 'stale-memory', 'intent-reality-gap', 'surface-freeze-violation'] },
  { id: 'C6', glob: 'INTENT.md, REQUIREMENTS.md, CLAUDE.md, MEMORY.md, README.md, CONTRIBUTING.md, smartai.md, CHANGELOG.md',
    lenses: ['stale-memory', 'intent-reality-gap', 'firewall/polarity-leak'] },
  { id: 'C7', glob: 'src/stream_manager/**/*.py',
    lenses: ['surface-freeze-violation', 'dormant-lever', 'cassette-coverage-gap', 'code-defect', 'firewall/polarity-leak'] },
  { id: 'C8', glob: 'rl/**/*.py, rl/schema.sql',
    lenses: ['firewall/polarity-leak', 'held-chain-deadlock', 'stale-memory', 'code-defect'] },
  { id: 'C9', glob: 'tools/*.py, tools/rl_test_helper/**',
    lenses: ['dormant-lever', 'cassette-coverage-gap', 'self-destructive', 'firewall/polarity-leak'] },
  { id: 'C10', glob: 'tests/**/*.py, tests/cassettes/**, beacons/**, golden/**, fixtures/**, conftest.py',
    lenses: ['cassette-coverage-gap', 'self-destructive', 'stale-memory', 'code-defect'] },
  { id: 'C11', glob: 'reports/soak-*.md, reports/replay-*.md, reports/alignment-eval-*.{md,json}, reports/poc-*.md',
    lenses: ['latency-regression', 'alignment-floor-erosion', 'dormant-lever', 'self-destructive'], readEvidenceOnly: true },
  { id: 'C12', glob: 'C:\\Users\\SeanHoppe\\.claude\\projects\\C--Users-SeanHoppe-VS-streamManager\\memory\\*.md',
    lenses: ['stale-memory', 'intent-reality-gap', 'held-chain-deadlock'], smInternalMemory: true },
  { id: 'C13', glob: 'docs/adr/ADR-5*.md',
    lenses: ['latency-regression', 'intent-reality-gap', 'stale-memory'] },
];

// ---- DIMENSIONS lens catalog (12 blind finders) -- section 4 ----
const DIMS = [
  { id: 'F1', lens: 'held-chain-deadlock',
    hint: 'A Seed/phase/issue carried N consecutive cycles on an unmet dependency. Confirm structural-unreachability via gate arithmetic (n_actual vs n_required, CI floor vs cap), not just "still open".',
    warStory: 'v10 P5 deferred 4 cycles on Seed v2.6-C; gate unreachable (n_actual=79/200, off-arm CI ~0.43 >> 0.10 cap, #177); Amendment D split the gate.' },
  { id: 'F2', lens: 'dormant-lever',
    hint: 'WIRED_LEVER_LEDGER dict (soak_driver.py) vs ADR-18 WIRED_LEVER_LEDGER_COUNT comment vs LEDGER_PRODUCTION_EXPECTED (ship_gate_runner.py) vs close-memory "HOLD N/0"; soak fire-rate 0%.',
    warStory: 'OQ-1 ledger drift; Haiku fast-path wired-but-unused v1.7->v1.9, DORMANT-3, force-ripped v2.0 P3.' },
  { id: 'F3', lens: 'surface-freeze-violation',
    hint: 'New caller path / reorder / non-additive change into a FROZEN module (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool, envelope schemas); RL reaching a FROZEN gov symbol.',
    warStory: 'ADR-18 minted after v1.7->v1.9 +2800 LOC on unfired FROZEN-seam levers; #131 gated on model_router.route reclass.' },
  { id: 'F4', lens: 'alignment-floor-erosion',
    hint: 'Sonnet/Haiku pass_rate in [0.80, 0.85] at n<6; n=6 escape-hatch not fired when prior pass_rate within 0.05 of FR-OG-7 0.80 floor.',
    warStory: 'v2.5 P2 BLOCK at Sonnet 0.7895 n=3; re-measured n=6 -> 0.9375 (measurement artefact). Drove the n=6 mandate.' },
  { id: 'F5', lens: 'cassette-coverage-gap',
    hint: 'New bus envelope kind in src/ without same-PR cassette_record.py + soak_driver.py extension; beacon/cassette desync.',
    warStory: 'v1.3 Learn Mode nearly tagged without LM cassette coverage; v1.3.0 re-shipped as v1.3.1.' },
  { id: 'F6', lens: 'stale-memory',
    hint: 'MEMORY/INTENT/REQUIREMENTS/ADR posture contradicted by code; FR-* with no enforcing symbol; "DONE/RESOLVED" the source falsifies; ledger doc lagging a landed PR.',
    warStory: 'v10-mvp-status.md still says P5 "0% BLOCKED 4th deferral" despite #214 landing P5 (24/24 green); FR-OG-7 silently degrades on fresh clone (.sm-context.yaml gitignored).' },
  { id: 'F7', lens: 'cross-PR-seam-gap',
    hint: 'Writer emits an envelope no consumer reads / reader expects a field no writer populates; only one end of a designed seam landed.',
    warStory: 'feedback_cross_pr_seam_review.md: feature branch reached main with one seam end; a subagent reported "all clean" over a silent revert.' },
  { id: 'F8', lens: 'firewall/polarity-leak',
    hint: 'certPortal vocab/paths/JOB-IDs/roles in SM source/tests/fixtures; a corpus/ingest path missing the polarity dual-key exclusion at SQL WHERE.',
    warStory: 'feedback_no_self_monitor.md (polarity-flip); feedback_certportal_dev_firewall.md + zero-contamination rule.' },
  { id: 'F9', lens: 'latency-regression',
    hint: 'From EXISTING reports only (no re-run): soak overall p95 > Seed v2.4-E 10.156s; L4 p95 > v2.4-F 22s; ADR-5 ceiling 15s.',
    warStory: 'v2.7.1 overall p95 10.480s breached v2.4-E; L4 22.49s tripped v2.4-F. v1.1 cold-start was misattributed to the hydrator.' },
  { id: 'F10', lens: 'self-destructive',
    hint: 'green-by-bypass: --cli-pool-size 0 default, PATHSPEC-UNSET passing the LOC gate vacuously, stale-fixture soak, glob-narrowing no-op, tautological assert.',
    warStory: 'PR #184 narrowed soak-*.md->soak-tmp-*.md but the driver writes soak-{iso_ts}.md (no-op); default --cli-pool-size 0 reproduces cold-start.' },
  { id: 'F11', lens: 'scaffolding-debt',
    hint: 'Unbound [ ] decision boxes, "deferred to a follow-up", TODO stubs, empty MEMORY.md sections; an orchestration prompt scheduling a >5min task in a fan-out subagent (subagent-escape-hatch / long-task-misplacement).',
    warStory: 'feedback_subagent_escape_hatches.md; feedback_subagent_long_task_abandonment.md.' },
  { id: 'F12', lens: 'code-defect',
    hint: 'A concrete logic bug not covered above: off-by-band helper, latency-path regression, deterministic-Python trainer leaking an LLM call.',
    warStory: 'feedback_cycle_tolerance_masks_bugs.md (off-by-bucket helper bug masked by feature-cycle LOC tolerance).' },
];

// ---- Schemas (StructuredOutput contracts) ----
const CATALOG_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['area', 'inventory', 'seeds'],
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
    seeds: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['lens', 'path', 'symptom'],
        properties: {
          lens: { type: 'string' },
          path: { type: 'string' },
          line: { type: 'string' },
          symptom: { type: 'string' },
        },
      },
    },
  },
};

const FIND_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['lens', 'candidates'],
  properties: {
    lens: { type: 'string' },
    candidates: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'lens', 'symptom', 'files', 'evidencePaths', 'rootCause'],
        properties: {
          id: { type: 'string' },
          lens: { type: 'string' },
          symptom: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          evidencePaths: { type: 'array', items: { type: 'string' } },
          rootCause: { type: 'string' },
          severity: { type: 'string', enum: ['BLOCKER', 'MAJOR', 'MINOR', 'unknown'] },
        },
      },
    },
  },
};

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['candidateId', 'verdict', 'evidence'],
  properties: {
    candidateId: { type: 'string' },
    verdict: { type: 'string', enum: ['CONFIRM', 'OVERSTATED', 'REFUTED'] },
    evidence: { type: 'string' },
  },
};

const VETTED_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'title', 'survives', 'type', 'scope', 'surfaceClass', 'invariantId', 'rootCause', 'evidencePaths', 'files', 'verifyCmd', 'binaryPass'],
  properties: {
    id: { type: 'string' },
    title: { type: 'string' },
    survives: { type: 'boolean' },
    type: { type: 'string', enum: ['code', 'process', 'gate'] },
    scope: { type: 'string', enum: ['v10-rl', 'v1.x-v2.x-main'] },
    surfaceClass: { type: 'string', enum: ['FROZEN', 'EVOLVING', 'EXPERIMENTAL', 'n/a'] },
    invariantId: { type: 'string' },
    rootCause: { type: 'string' },
    evidencePaths: { type: 'array', items: { type: 'string' } },
    files: { type: 'array', items: { type: 'string' } },
    verifyCmd: { type: 'string' },
    binaryPass: { type: 'string' },
    severity: { type: 'string', enum: ['BLOCKER', 'MAJOR', 'MINOR', 'unknown'] },
    refuteSummary: { type: 'string' },
  },
};

// ---- Helpers ----
function candKey(c) {
  const f = (c.files && c.files[0]) || '';
  const s = (c.symptom || '').slice(0, 50).toLowerCase().replace(/\s+/g, ' ').trim();
  return `${c.lens}|${f}|${s}`;
}

function groupSeedsByLens(catalogues) {
  const byLens = {};
  for (const cat of catalogues) {
    for (const s of (cat.seeds || [])) {
      (byLens[s.lens] = byLens[s.lens] || []).push(s);
    }
  }
  return byLens;
}

function dedupeById(finds) {
  const seen = new Map();
  for (const c of finds) {
    const k = candKey(c);
    if (!seen.has(k)) seen.set(k, c);
  }
  return [...seen.values()];
}

function FIND_PROMPT(d, seeds, already, round) {
  return `${SAFETY}

Blind finder for lens "${d.lens}" (${d.id}). Anchor ${ANCHOR} (read-only). Round ${round + 1}/3.
WHAT TO HUNT: ${d.hint}
SM war-story this lens catches (pattern reference, not the only instance): ${d.warStory}
Cataloguer seeds pre-tagged for your lens (may be empty -- do not stop at these): ${JSON.stringify((seeds || []).slice(0, 40))}
Already found this lens (return NEW, distinct issues only; do NOT repeat these): ${JSON.stringify((already || []).map((c) => c.id))}

Coverage-by-kind, not by-luck: sweep the lens's whole scope, not the first hit.
QUALITY BAR (reject anything below it): each candidate needs >=2 evidence paths (file:line / SHA / PR# / Seed-ID)
AND a root cause (one sentence WHY, not the symptom). id must be globally unique, e.g. "${d.id}-<area>-<n>".
If you find nothing new this round, return candidates: [].`;
}

// ===== Stage 1: CATALOG -- one read-only cataloguer per area (barrier; finders need the map) =====
phase('Catalog');
const catalogues = (await parallel(CORPUS.map((a) => () =>
  agent(`${SAFETY}

Cataloguer for ${a.id}. Globs: ${a.glob}
Anchor ${ANCHOR} (read-only, pinned). Inventory every matching artefact: {path, kind, status=live|stale|dead|unknown}.
Tag candidate gaps with the applicable lenses from: [${a.lenses.join(', ')}].
${a.readEvidenceOnly ? 'EVIDENCE-ONLY: read existing report files as FROZEN evidence; NEVER trigger a soak/eval run. ' : ''}${a.smInternalMemory ? 'SM-OWN auto-memory dir (outside the repo tree). FAIL LOUD (return empty inventory + a single seed noting absence) if the dir does not exist rather than wandering to a sibling. Stamp EVERY seed symptom with "scope=local-only/non-CI-reproducible". ' : ''}Return per-area inventory + candidate seeds {lens, path, line, symptom}, each seed with >=1 evidence path in symptom.`,
    { label: `catalog:${a.id}`, phase: 'Catalog', agentType: 'Explore', schema: CATALOG_SCHEMA })
))).filter(Boolean);
const seedsByLens = groupSeedsByLens(catalogues);
log(`CATALOG: ${catalogues.length}/${CORPUS.length} areas inventoried; `
  + `${Object.values(seedsByLens).reduce((n, a) => n + a.length, 0)} pre-tagged seeds across ${Object.keys(seedsByLens).length} lenses`);

// ===== Stage 2: FIND -- one BLIND finder per lens, loop-until-dry <=3 rounds (barrier) =====
async function loopUntilDry(d, seeds, maxRounds) {
  const found = [];
  const seen = new Set();
  for (let round = 0; round < maxRounds; round++) {
    const r = await agent(FIND_PROMPT(d, seeds, found, round), {
      label: `find:${d.id}:r${round + 1}`, phase: 'Find', agentType: 'Explore', schema: FIND_SCHEMA,
    });
    const cands = (r && r.candidates) || [];
    const fresh = cands.filter((c) => !seen.has(candKey(c)));
    if (!fresh.length) break; // dry round -> stop early
    fresh.forEach((c) => { seen.add(candKey(c)); found.push({ ...c, lens: d.lens }); });
  }
  return found;
}

phase('Find');
const rawFinds = (await parallel(DIMS.map((d) => () => loopUntilDry(d, seedsByLens[d.lens], 3))))
  .filter(Boolean).flat();
const candidates = dedupeById(rawFinds);
log(`FIND: ${rawFinds.length} raw candidates -> ${candidates.length} deduped across ${DIMS.length} lenses`);

// ===== Stage 3: VERIFY -- 2 isolated refuters + adjudicator per candidate (pipeline, no barrier) =====
const VERIFY_CAP = 60;
const toVerify = candidates.slice(0, VERIFY_CAP);
if (candidates.length > VERIFY_CAP) {
  log(`VERIFY cap: ${candidates.length} candidates; verifying first ${VERIFY_CAP}, `
    + `${candidates.length - VERIFY_CAP} DEFERRED (logged, not silently dropped) -- re-run audit to cover them`);
}

phase('Verify');
const vetted = await pipeline(
  toVerify,
  (cand) => parallel([
    () => agent(`${SAFETY}

Refuter A for candidate ${cand.id} [lens=${cand.lens}]. Your job is to REFUTE, not to agree.
Claim: ${cand.symptom}
Asserted root cause: ${cand.rootCause}
Files: ${JSON.stringify(cand.files)}   Evidence: ${JSON.stringify(cand.evidencePaths)}
Open the cited files on HEAD (anchor ${ANCHOR}). Hunt a contradiction: the code/doc already handles X; the
cited line actually says Y; the finding is stale vs HEAD; the claim is overstated.
Return CONFIRM (claim holds -- cite the line) | OVERSTATED (partly true -- say exactly what is wrong) |
REFUTED (decisive contradiction -- cite file:line).`,
      { label: `refute:${cand.id}:A`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA }),
    () => agent(`${SAFETY}

Refuter B for candidate ${cand.id} [lens=${cand.lens}]. ISOLATED from refuter A. Same REFUTE mandate.
Claim: ${cand.symptom}
Files: ${JSON.stringify(cand.files)}   Evidence: ${JSON.stringify(cand.evidencePaths)}
Independently verify on HEAD (anchor ${ANCHOR}).
Return CONFIRM | OVERSTATED | REFUTED with a file:line.`,
      { label: `refute:${cand.id}:B`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA }),
  ]).then((v) => v.filter(Boolean)),
  (verdicts, cand) => agent(`${SAFETY}

${TOOLCHAIN}

Adjudicator for candidate ${cand.id} [lens=${cand.lens}].
Original claim: ${cand.symptom}
Asserted root cause: ${cand.rootCause}
Files: ${JSON.stringify(cand.files)}   Evidence: ${JSON.stringify(cand.evidencePaths)}
Refuter verdicts: ${JSON.stringify(verdicts)}

DECISION RULE: survives=false ONLY on a decisive REFUTED backed by a real file:line contradiction.
OVERSTATED -> survives=true but tighten the claim and root cause. CONFIRM -> survives=true.
If it survives, stamp ALL fields:
- title: one-line summary.
- type: code | process | gate. (gate = needs a Tier-3 soak / real alignment-eval / FROZEN freeze-lift.)
- scope: v10-rl | v1.x-v2.x-main.
- surfaceClass: ADR-18 class of the touched file(s) -- FROZEN | EVOLVING | EXPERIMENTAL | n/a.
- invariantId: FR-OG-7 0.80 | NFR-P2 15s | ADR-18 Rule N | Amendment A/C/D | WIRED_LEVER_LEDGER_COUNT | n/a.
- rootCause: one sentence WHY (not symptom).
- evidencePaths: >=2 (file:line / SHA / PR# / Seed-ID).
- files: type=code -> code paths only; type=process -> the prompt/doc/config + the violated rule;
         type=gate -> the ship-gate Sn step or the unreachable gate arithmetic.
- verifyCmd + binaryPass: from the TOOLCHAIN library above (type=gate may name the main-thread command).`,
    { label: `adjudicate:${cand.id}`, phase: 'Verify', agentType: 'Explore', schema: VETTED_SCHEMA }),
);

// ===== Stage 4: REPORT -- return survivors to MAIN THREAD (which writes MVP-GAP-REPORT.md) =====
const survivors = vetted.filter(Boolean).filter((f) => f.survives);
const byType = survivors.reduce((m, f) => { m[f.type] = (m[f.type] || 0) + 1; return m; }, {});
log(`VERIFY: ${survivors.length}/${toVerify.length} survived adversarial refute `
  + `(code=${byType.code || 0}, process=${byType.process || 0}, gate=${byType.gate || 0})`);

phase('Report');
return {
  anchor: ANCHOR,
  counts: {
    cataloguers: catalogues.length,
    rawFinds: rawFinds.length,
    deduped: candidates.length,
    verified: toVerify.length,
    deferred: Math.max(0, candidates.length - VERIFY_CAP),
    survivors: survivors.length,
    byType,
  },
  survivors,
};
