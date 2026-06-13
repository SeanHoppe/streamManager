// sm-mvp-shipgate -- Workflow 3 (cycle-close automation). Orchestrates S0-S13 as three lanes so a
// cycle can tag vN.M.0. LANE A = automatable read-only static checks (exit-code binary, zero claude -p,
// <60s each): preflight, S0.5 anchor re-pin, wipe dry-run, inspect-soak, loc, ledger, S6-OQ1 reconcile,
// s6.5, align --dry-run, FROZEN surface audit, fast-tests, ledger-drift, ruff, mypy, regression close-votes.
// LANE B = MAIN-THREAD-ONLY (>5min real claude): S2 Tier-3 soak, S4 align --execute -- EMITTED as argv +
// ScheduleWakeup handoff, never run in a subagent. LANE C = OPERATOR-BOUND: cycle-type, S7 ADR-5 append,
// S9 git tag (irreversible), OQ-1 disposition. ASCII-only. See streamManagerworkflow.md sec 3 (W3).
//
// INVOKE: Workflow({ scriptPath: '.../sm-mvp-shipgate.js', args: {
//   anchor: '70e23e5', expectedBranch: 'ship/v2.8-p3-ship-gate', tag: 'v2.8.0',
//   postSoak: false, soakReport: '<path>', alignReport: '<path>'   // set for the post-soak re-entry (Adjudicate)
// }})
export const meta = {
  name: 'sm-mvp-shipgate',
  description: 'Cycle-close: lane-A read-only static ship-gate (preflight..mypy + S0.5 anchor re-pin + S6-OQ1 reconcile + frozen audit), lane-B main-thread soak+align handoff, lane-C operator decisions. Never runs the soak/eval in a subagent.',
  phases: [{ title: 'Lane-A static' }, { title: 'Adjudicate' }],
};

const ANCHOR = (args && args.anchor) || '70e23e5';
const EXPECTED_BRANCH = (args && args.expectedBranch) || 'ship/v2.8-p3-ship-gate';
const TAG = (args && args.tag) || 'v2.8.0';
const POST_SOAK = !!(args && args.postSoak);

const SAFETY = [
  'READ-ONLY static lane: Read/Grep/Bash(read-only). The ONLY destructive ship-gate step (wipe --apply) is NOT run here; wipe is dry-run only.',
  'FIREWALL (G1): never touch **/certPortal/**. POLARITY (G2): SQL WHERE dual-key self-exclusion. ASCII-only (G11).',
  'LONG-TASK (G7): NEVER run a Tier-3 soak or `align --execute` (real claude -p). align is --dry-run ONLY here (resolves --runs 6 with zero claude calls).',
  'Map verdicts: rc==0 -> PASS; rc==2 -> BLOCK; rc==1 -> BLOCK for static checks (exit1IsBlock), WARN only for the loc gate (1500<net<=2250).',
].join('\n');

const SOAK_CMD = `BRIDGE_API_GOV=1 BRIDGE_CYCLE_TIP_SHA=${ANCHOR} BRIDGE_CYCLE_TYPE=feature BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/ ` +
  `python tools/soak_driver.py --port 8766 --cli-pool-size 2 --total-seconds 1800 --interval-seconds 30`;
const ALIGN_CMD = 'python -m tools.ship_gate_runner align --execute';

const ROWS_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['rows', 'blocked'],
  properties: {
    rows: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['step', 'verdict', 'detail'],
      properties: { step: { type: 'string' }, verdict: { type: 'string', enum: ['PASS', 'WARN', 'BLOCK'] }, detail: { type: 'string' } } } },
    blocked: { type: 'array', items: { type: 'string' } },
    oq1: { type: 'string' },
  },
};

if (!POST_SOAK) {
  // ===== LANE A: one read-only runner agent executes every static check sequentially (shared tree) =====
  phase('Lane-A static');
  const laneA = await agent(`${SAFETY}

Run the LANE-A static ship-gate at anchor ${ANCHOR}. Execute each, capture exit code, map to PASS/WARN/BLOCK, return rows[]:
- S0   preflight:        python -m tools.ship_gate_runner preflight
- S0.5 anchor re-pin:    BLOCK unless tools/ship_gate_runner.py CYCLE_TIP_SHA startswith ${ANCHOR} AND EXPECTED_BRANCH == "${EXPECTED_BRANCH}".
                         (Known-stale today: CYCLE_TIP_SHA=4902cca / ship/v2.7-p3-ship-gate -> expect BLOCK until re-pinned.)
- S1   wipe dry-run:     python -m tools.ship_gate_runner wipe        (NO --apply)
- S3   inspect-soak:     python -m tools.ship_gate_runner inspect-soak  (newest reports/soak-*.md; PASS if a report exists)
- S5   loc (binding):    python -m tools.ship_gate_runner loc          (rc1 => WARN 1500<net<=2250, NOT block; rc2 => BLOCK)
- S6   ledger soak-scope: python -m tools.ship_gate_runner ledger
- S6-OQ1 reconcile:      read the SOAK ledger size via AST (delegate to ship_gate_runner._read_soak_ledger_dict_size(); NEVER a flat-brace {[^}]*} regex),
                         read the ADR-18 WIRED_LEVER_LEDGER_COUNT comment, read LEDGER_PRODUCTION_EXPECTED (ship_gate_runner.py:75), read the
                         production-lever claim in the active close/next-steps doc. BLOCK unless soak_count==adr_count AND prod_expected==prod_claimed
                         AND (prod_expected==soak_count OR a docs/v2.8-ledger-reconcile.md enumerating the production levers exists). Put the finding in oq1.
- S6.5 seed diagnosis:   python -m tools.ship_gate_runner s6.5
- S4   align --dry-run:  python -m tools.ship_gate_runner align --dry-run   (resolves --runs 6, ZERO claude calls; never --execute here)
- FROZEN surface audit:  hunk-aware diff ${ANCHOR}..HEAD on governance.py/message_bus.py/cli_governance.py/model_router.py/cli_pool.py/envelope_kinds.py:
                         additive-only=PASS; new-caller-edge=reroute(#131) -> WARN+note; band/schema reorder=BLOCK.
- fast-tests:            python -m pytest -m "not slow and not alignment_eval" -q
- ledger-drift test:     python -m pytest tests/test_dormant_ledger_consistency.py -q
- ruff:                  python -m ruff check src tests tools dashboard rl
- mypy:                  python -m mypy
- regression close-votes: parse EXISTING newest soak p95 vs Seed v2.4-E 10.156s (overall) / v2.4-F 22s (L4) -> WARN on breach (carry-forward note, not block).
Return rows[] + blocked[] (steps with verdict BLOCK) + oq1.`,
    { label: 'lane-A', phase: 'Lane-A static', agentType: 'general-purpose', schema: ROWS_SCHEMA });

  return {
    lane: 'A-static',
    anchor: ANCHOR,
    rows: laneA ? laneA.rows : [],
    blocked: laneA ? laneA.blocked : ['lane-A runner failed'],
    oq1: laneA ? laneA.oq1 : 'unknown',
    handToMainThread: [   // LANE B -- main thread fires these via run_in_background + ScheduleWakeup, NOT a subagent
      { step: 'S2 Tier-3 soak', cmd: SOAK_CMD, pass: 'Verdict: PASS, degrade_count=0', runVia: 'run_in_background + ScheduleWakeup' },
      { step: 'S4 align --execute (n=6)', cmd: ALIGN_CMD, pass: 'ci-gate exit 0 AND adjusted Sonnet pass-rate >= 0.80', runVia: 'run_in_background + ScheduleWakeup' },
    ],
    operatorDecisions: [   // LANE C -- surfaced, never auto-flipped
      'cycle-type call (feature|consolidation)',
      'S6-OQ1 disposition (reconcile artefact vs correct LEDGER_PRODUCTION_EXPECTED to 0)',
      'S7 ADR-5 latency-baseline append',
      `S9 git tag -a ${TAG} (IRREVERSIBLE)`,
    ],
    note: 'Lane-A is static only. After the main thread returns the soak + align reports, re-invoke with args.postSoak=true + soakReport/alignReport for Adjudicate.',
  };
}

// ===== Post-soak re-entry: Adjudicate (re-run inspect-soak + parse align result + regression close-votes) =====
phase('Adjudicate');
const ADJ_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['soakVerdict', 'alignPassRate', 'frOg7Block', 'regressionNotes', 'shipReady'],
  properties: {
    soakVerdict: { type: 'string' },
    alignPassRate: { type: 'string' },
    frOg7Block: { type: 'boolean' },
    regressionNotes: { type: 'array', items: { type: 'string' } },
    shipReady: { type: 'boolean' },
    correctiveSubPhase: { type: 'string' },
  },
};
const adj = await agent(`${SAFETY}

POST-SOAK adjudicate (read existing reports ONLY; no re-run). soakReport=${(args && args.soakReport) || 'newest reports/soak-*.md'}; alignReport=${(args && args.alignReport) || 'newest reports/alignment-eval-*.json'}.
- inspect-soak: python -m tools.ship_gate_runner inspect-soak --path <soakReport> ; capture Verdict + degrade_count.
- align result: parse adjusted Sonnet pass-rate. FR-OG-7 floor 0.80 is the SHIP-BLOCKER. align exit 2 (pass-rate < 0.80) => fold a vN.M.1 corrective sub-phase (v1.3.1/v2.5.1/v2.7.1 precedent).
- regression close-votes: overall p95 vs Seed v2.4-E 10.156s; L4 vs v2.4-F 22s.
- EXPERIMENTAL rl/ failures CANNOT block this main-cycle ship-gate.
Return soakVerdict, alignPassRate, frOg7Block, regressionNotes[], shipReady, correctiveSubPhase (if any).`,
  { label: 'adjudicate', phase: 'Adjudicate', agentType: 'general-purpose', schema: ADJ_SCHEMA });

return {
  lane: 'post-soak-adjudicate',
  anchor: ANCHOR,
  result: adj,
  operatorDecisions: adj && adj.shipReady
    ? [`S7 ADR-5 append`, `S9 git tag -a ${TAG} (IRREVERSIBLE) -- operator only`]
    : [`align/soak gate not met -> ${adj ? adj.correctiveSubPhase || 'investigate' : 'rerun'}; do NOT tag`],
};
