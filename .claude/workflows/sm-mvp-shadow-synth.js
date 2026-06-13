// sm-mvp-shadow-synth -- Workflow 4 (soak-substitute; SM-native, outside-the-lines). Generates
// infra-validation + regression evidence so the v10 chain advances WITHOUT burning a live Tier-3 soak,
// while leaving the pre-registered v10.3 promotion criteria UNTOUCHED. All offline, firewall- and
// polarity-clean, no live session, no claude -p. Every shadow write is tagged soak_run_id/--mode=v10.1
// (Amendment D excludes v10.1 rows from v10.3 writeback). robin (G9) owns the final ship-criteria read.
// EXPERIMENTAL rl/ only -- CANNOT block the main ship-gate, CANNOT satisfy a pre-registered criterion.
// ASCII-only (cp1252). See streamManagerworkflow.md sec 6.
//
// INVOKE: Workflow({ scriptPath: '.../sm-mvp-shadow-synth.js', args: {
//   episodesDb: 'rl_episodes.db', shadowDb: 'rl_shadow.db', manifests: 'rl_proposals/',
//   candidate: '<proposal.json>', baseline: '<thresholds.json>', cassettePack: 'tests/cassettes/safety'
// }})
export const meta = {
  name: 'sm-mvp-shadow-synth',
  description: 'Soak-substitute: OPE + cassette-shadow + synthetic-fixture + bootstrap + micro-soak + cassette-align proxy. Offline, --mode=v10.1 infra-validation only. NEVER satisfies pre-registered v10.3 ship criteria (real Tier-3 soak does). robin owns the criteria read.',
  phases: [{ title: 'Precheck' }, { title: 'OPE' }, { title: 'Shadow-replay' }, { title: 'Bootstrap' }, { title: 'Verdict' }],
};

const EPISODES = (args && args.episodesDb) || 'rl_episodes.db';
const SHADOW = (args && args.shadowDb) || 'rl_shadow.db';
const MANIFESTS = (args && args.manifests) || 'rl_proposals/';
const CAND = (args && args.candidate) || '<candidate proposal>';
const BASE = (args && args.baseline) || '<baseline thresholds>';
const PACK = (args && args.cassettePack) || 'tests/cassettes/safety';

const SAFETY = [
  'OFFLINE ONLY. No live Claude CLI session, no claude -p, no Tier-3 soak. Read/Grep/Bash + the named offline tools (which MAY write rl_shadow.db / reports).',
  'AUTONOMOUS STEP: you are a non-interactive workflow agent -- there is NO interactive user to answer you. EXECUTE the named command(s) and report the result. NEVER reply asking for clarification; if a path/command is missing, run what you can and return ran:false with the concrete error string.',
  'FIREWALL (G1): never touch **/certPortal/**. ASCII-only (G11).',
  'POLARITY (G2): when reading ' + EPISODES + ', EXCLUDE SM-self at SQL WHERE. NOTE: the episodes schema has NO project_slug column ' +
    '(validated), so the only available dual-key is `WHERE session_id != BRIDGE_SM_SELF_SESSION_ID`; tier-1 (episode_logger write-refusal) ' +
    'is the primary guard. If any SM-self session_id row is present, that is a loud FAIL -- stop and surface.',
  'INTEGRITY FIREWALL: every shadow write tagged soak_run_id/--mode=v10.1. NEVER relax a pre-registered v10.3 criterion based on observed/synthetic data.',
].join('\n');

// ===== Precheck: corpus polarity sanity (loud-fail on any SM-self row) =====
phase('Precheck');
const PRECHECK_SCHEMA = { type: 'object', additionalProperties: false, required: ['episodeCount', 'smSelfRows', 'clean'],
  properties: { episodeCount: { type: 'string' }, smSelfRows: { type: 'string' }, clean: { type: 'boolean' }, note: { type: 'string' } } };
const pre = await agent(`${SAFETY}

Precheck ${EPISODES}: count episodes; count rows whose session_id == $BRIDGE_SM_SELF_SESSION_ID (or any STREAM_MANAGER session). ` +
  `clean=true iff smSelfRows==0. Return episodeCount, smSelfRows, clean, note. Do NOT proceed-implying anything; just report.`,
  { label: 'precheck-polarity', phase: 'Precheck', agentType: 'Explore', schema: PRECHECK_SCHEMA });
if (pre && pre.clean === false) {
  log(`PRECHECK FAIL: SM-self rows in corpus (${pre.smSelfRows}) -- polarity breach, halting shadow-synth.`);
  return { halted: true, reason: 'polarity breach in episodes corpus', precheck: pre };
}
log(`PRECHECK: ${pre ? pre.episodeCount : '?'} episodes, ${pre ? pre.smSelfRows : '?'} SM-self rows (clean).`);

// ===== Stages 1-6 of section 6, fanned out then adjudicated =====
const RUN_SCHEMA = { type: 'object', additionalProperties: false, required: ['name', 'ran', 'result'],
  properties: { name: { type: 'string' }, ran: { type: 'boolean' }, result: { type: 'string' }, advisoryOnly: { type: 'boolean' } } };

phase('OPE');
// (1) OPE-first offline evaluation -- the DESIGNED mechanism; substitutes for shadow on everything except true on-policy divergence.
const ope = await agent(`${SAFETY}

(1) OPE offline evaluation against ${EPISODES}: run the 5-stage gauntlet:
  python -m rl.cli.validate --candidate ${CAND} --baseline ${BASE} --db ${EPISODES}
Report IPS/DR candidate-vs-baseline reward estimate, HITL agreement, FR-OG-7 violation count. EXPERIMENTAL -> advisory.`,
  { label: 'ope', phase: 'OPE', agentType: 'general-purpose', schema: RUN_SCHEMA });

phase('Shadow-replay');
// (2) cassette-replay shadow + (3) synthetic-fixture (Path-D) -> rl_shadow.db -> check_criteria end-to-end.
const replay = (await parallel([
  () => agent(`${SAFETY}

(2) Cassette-replay shadow: drive rl/shadow.py ShadowRecorder from tools/cassette_replay.py (--pack ${PACK}) instead of a live soak: ` +
    `replay recorded bus envelopes through bus.subscribe_decision -> ShadowRecorder writes ${SHADOW} tuples (deterministic, in-process). ` +
    `Tag soak_run_id/--mode=v10.1. This proves the harness + closes the INFRASTRUCTURE side of #112.`,
    { label: 'cassette-shadow', phase: 'Shadow-replay', agentType: 'general-purpose', schema: RUN_SCHEMA }),
  () => agent(`${SAFETY}

(3) Synthetic-fixture (Path-D) replay: python tools/path_d_verify.py --json (lineage clean, exit 0) then run check_criteria against the ` +
    `synthetic fixture: python -m rl.cli.check_criteria --shadow-db ${SHADOW} --manifests ${MANIFESTS}. CI-repeatable, fully offline.`,
    { label: 'synthetic-fixture', phase: 'Shadow-replay', agentType: 'general-purpose', schema: RUN_SCHEMA }),
  () => agent(`${SAFETY}

(5) Micro-soak tier (ADR-17 new tier; not a promotion vehicle): a cassette-fed end-to-end bus run completing in seconds, ` +
    `fast regression canary between rare real Tier-3s. Report pass/fail + timing.`,
    { label: 'micro-soak', phase: 'Shadow-replay', agentType: 'general-purpose', schema: RUN_SCHEMA }),
  () => agent(`${SAFETY}

(6) Cassette-replay alignment proxy: use recorded alignment cassettes (tests/cassettes/, tools/cassette_replay.py) to compute a FAST ` +
    `pass-rate PROXY in-workflow. CAVEAT: catches regression vs the recorded baseline ONLY, not live model drift; the real n=6 still gates ` +
    `the actual ship. Flag any regression vs the recorded baseline.`,
    { label: 'align-proxy', phase: 'Shadow-replay', agentType: 'general-purpose', schema: RUN_SCHEMA }),
])).filter(Boolean);

phase('Bootstrap');
// (4) bootstrap / block-resampling windows -- ADVISORY confidence proxy that de-risks BEFORE a real soak; NOT a pre-registration satisfier.
const boot = await agent(`${SAFETY}

(4) Bootstrap / block-resampling: partition the ${EPISODES} corpus into 3 temporal blocks (or block-bootstrap resample); run ` +
  `python -m rl.cli.check_criteria --shadow-db ${SHADOW} --manifests ${MANIFESTS} per block; require all 3 PASS. ` +
  `This is an ADVISORY confidence proxy (advisoryOnly=true). It is NOT the pre-registered "3 consecutive Tier-3 shadow" satisfier.`,
  { label: 'bootstrap-windows', phase: 'Bootstrap', agentType: 'general-purpose', schema: RUN_SCHEMA });

// ===== Verdict: robin (G9) owns the ship-criteria read; integrity firewall keeps the two ledgers separate =====
phase('Verdict');
const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['infraValidation', 'regressionClean', 'feasibility', 'criteriaRead', 'STILL_NEEDS'],
  properties: {
    infraValidation: { type: 'string' },
    regressionClean: { type: 'boolean' },
    feasibility: { type: 'string' },
    criteriaRead: { type: 'string' },      // robin's check_criteria summary (which of 6 PASS), advisory
    entryGatePredicate: { type: 'string' },// is_ready_for_shadow_v10_1() status
    STILL_NEEDS: { type: 'string' },
  },
};
const verdict = await agent(`${SAFETY}

You are robin (v10 RL verification owner, G9). Read-only. Adjudicate the offline shadow-synth evidence; NEVER relax a pre-registered criterion.
Inputs: OPE=${JSON.stringify(ope)}; replay=${JSON.stringify(replay)}; bootstrap=${JSON.stringify(boot)}.
- Run/parse python -m rl.cli.check_criteria --shadow-db ${SHADOW} --manifests ${MANIFESTS} (exit 0 = all 6 PASS) -- report which of the 6 criteria pass (ADVISORY infra-validation, --mode=v10.1).
- Check the entry-gate predicate: is_ready_for_shadow_v10_1() on rl/bandit.py (validated ABSENT today -- only is_ready_for_shadow() exists). Note whether it was added.
- Assemble the INFRA-VALIDATION / REGRESSION ledger ONLY. State explicitly that NONE of this counts toward v10.3 writeback promotion (Amendment D ignores --mode=v10.1 rows).
- STILL_NEEDS must state: "3x real Tier-3 shadow soak + real n=6 alignment-eval (main thread, human-gated)".`,
  { label: 'robin-verdict', phase: 'Verdict', agentType: 'robin', schema: VERDICT_SCHEMA });

return {
  mode: 'v10.1-infra-validation',
  precheck: pre,
  ope,
  replay,
  bootstrap: boot,
  verdict,
  integrityFirewall: 'infra-validation/regression ledger ONLY; pre-registered v10.3 criteria UNTOUCHED; --mode=v10.1 rows excluded from writeback.',
  STILL_NEEDS: verdict ? verdict.STILL_NEEDS : '3x real Tier-3 shadow soak + real n=6 alignment-eval (main thread, human-gated)',
};
