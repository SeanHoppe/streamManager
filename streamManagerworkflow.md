# streamManager -- MVP-100 workflow proposal

> **Document type:** prompt / workflow-suite proposal (aspirational, not yet wired).
> **Aspirational reference:** `Claude-ResearchFixWorkflow.md` (certPortal `/report-research`
> + `/report-fixes`). The control-flow architecture there is generic; this proposal
> retargets it to streamManager by rewriting the four swap points (CORPUS map,
> DIMENSIONS lenses, HOUSE_STYLE invariant IDs, TOOLCHAIN) and adds two SM-native
> workflows the certPortal pattern has no analog for.
> **Authoring basis:** repo HEAD `d8ed70f`; cycle-tip anchor `70e23e5` (v2.8 P0, #211);
> verified by a 14-agent map -> draft -> adversarial-review workflow (5 corpus/toolchain
> maps, 5 drafts, 4 adversarial reviewers). All review BLOCKER/MAJOR findings folded in
> (see section 9).
> **ASCII-only (cp1252).** No smart quotes, em-dashes (write `--`), box-drawing, or U+00A7.

---

## 0. What this proposes (TL;DR)

A four-workflow suite that drives streamManager to MVP 100% under its own governance
discipline, instead of by ad-hoc cycles:

| Workflow | Half | Role |
|---|---|---|
| `/sm-mvp-audit` | research | Read-only corpus survey -> SM-specific failure-mode finders -> adversarial refute -> `MVP-GAP-REPORT.md` (the input contract). |
| `/sm-mvp-converge` | fix + ship | Union-find partition the report -> file-disjoint parallel minimal edits -> refute x2 -> targeted tests -> PR. Never main, never force-push. |
| `/sm-mvp-shipgate` | cycle-close | Deterministic S1-S13 ship-gate: auto-runs the read-only verification lane, hands the >5min soak + alignment-eval back to the main thread, surfaces operator-bound tag decisions. |
| `/sm-mvp-shadow-synth` | soak-substitute | **(SM-native, outside-the-lines)** Generates infra-validation + regression evidence (OPE on the logged corpus, cassette-replay shadow, synthetic-fixture, bootstrap windows, micro-soak) so the chain advances WITHOUT burning a live Tier-3 soak -- while keeping the pre-registered promotion criteria untouched. See section 6. |

The single load-bearing design constraint that reshapes all four: **a Tier-3 soak and a
real `claude -p` alignment-eval are >5min long tasks; they MUST run from the main thread
via `run_in_background` + `ScheduleWakeup` and CANNOT live in a fan-out subagent** (subagents
abandon long tasks -- `feedback_subagent_long_task_abandonment.md`). So every workflow keeps
its fan-out subagents read-only and bounded, and hands long-task / gate work back to the
main thread.

---

## 1. MVP-100 reality check (what "100%" actually gates on)

There are two MVP scopes in this repo. "MVP 100%" anchors on scope (a).

**Scope (a) -- v10 RL companion-track MVP.** Authoritative ledger `docs/v10-mvp-status.md`.
The ledger states **~80%** (equal-weighted `(100x5 + 85 + 0)/7 = 83.6%`), with P5 recorded
as "0%, BLOCKED on Seed v2.6-C, 4th consecutive deferral", last-refresh 2026-05-21.

**The ledger is STALE.** `git show --stat` confirms commit `07ee05c` (#214,
"feat(v2.8-p1): Path-D synthetic-fixture v10 P5 implementation") landed the P5
infrastructure: `rl/shadow.py` (ShadowRecorder, 50ms non-invasion budget, WAL `rl_shadow.db`),
`rl/stop_conditions.py` (the SIX pre-registered ship criteria), `rl/cli/shadow.py`,
`rl/cli/check_criteria.py` (exit 0 = ALL PASS), and the `tools/soak_driver.py`
`--shadow-recorder` / `--shadow-proposal` hooks -- 24/24 tests green on HEAD. So the P5 *code*
is done; recompute is **~95-96% infrastructure-complete**. The true remaining blocker is no
longer code -- it is the **empirical shadow soak** (3 consecutive Tier-3 shadows + 6 ship
criteria) that closes **#112**, i.e. data, not implementation.

**The held chain to v10 100%:**

```
#112 (P5 shadow A/B run + 6 ship criteria x3 Tier-3)   <- INFRA LANDED #214; needs empirical run
   `-- #131 (v10.x cycle frame = ADR-18 FROZEN->EVOLVING freeze-lift of model_router.route)
          |-- #124 (wire BRIDGE_L4_FALLBACK_CONFIDENCE + un-ADVISORY OPE stage-1)
          `-- #125 (restore Ridge-Q DR estimator)
```

Minor entry-gate gap: ADR-18 Amendment D specified a sibling `is_ready_for_shadow_v10_1()`
predicate on the bandit; `rl/bandit.py` only has the original `is_ready_for_shadow()`. The
v10.1-mode infra-validation gate predicate was not added (only `stop_conditions.py` landed).

**Scope (b) -- v1.x/v2.x main-cycle MVP.** No single percentage anchor. Completeness =
ADR-18-disciplined cycle-after-cycle shipping. The immediate gate is finishing **v2.8**:
P2 (env-split `BRIDGE_CLI_TIMEOUT` prod 30s / `BRIDGE_CLI_TIMEOUT_EVAL` eval 60s +
Seed v2.7-A-CLIP corpus n=12 re-measure) then P3 ship-gate -> tag **v2.8.0** (no `v2.8.0`
tag exists yet; latest is `v2.7.1`). Current cycle-tip LOC = **+1617 insertions** against
`70e23e5`, already past the soft 1500 (WARN band; BLOCK at 2250) -- surfaced under an
Amendment A operator override from the #216 POC-fleet bundle.

**Gauge note (per `docs/2026-05-22-guage-notes.md` DV-3):** percentage completion is NOT
the load-bearing metric. The schedule estimators are **cycles-to-v10-P5-land**,
**cycles-to-first-FROZEN-reclass** (model_router.route at #131), and
**cycles-to-ship-criteria-PASS-x3** (#112). The report house-style pins these, not "X% to 100%".

---

## 2. The retarget thesis (generic control flow, four SM swap points)

The certPortal `/report-research` + `/report-fixes` architecture is reused unchanged:
fan-out cataloguers, loop-until-dry blind finders, isolated adversarial refuters + an
adjudicator, survivors-only routed report; then union-find file-partitioning, minimal
confined edits, adversarial fix-review, bounded repair, targeted tests, PR. Only the four
swap points are rewritten for SM:

1. **CORPUS map** -- SM paths (docs/ADRs/prompts/seeds/jobs/root-law/src/rl/tools/tests/
   reports-as-evidence/SM-auto-memory). See section 3, W1.
2. **DIMENSIONS lenses** -- SM failure modes with real SM war-stories. See section 4.
3. **HOUSE_STYLE invariant IDs** -- ADR-18 freeze classes, FR-/NFR- IDs, firewall + polarity,
   cycle-tip LOC anchor, cassette-coverage, n=6 alignment, long-task rule. See section 5.
4. **TOOLCHAIN** -- `pytest -m`, `ruff`, `mypy`, `ship_gate_runner.py` subcommands,
   `soak_driver.py`, `alignment_eval.py`, `rl/cli/*`, `path_d_verify.py`. Verified command
   library below.

### Verified TOOLCHAIN command library (every finding cites one)

| Name | Invocation | Binary pass | Long-running? |
|---|---|---|---|
| fast-test | `python -m pytest -m "not slow and not alignment_eval" -q` | exit 0 | no |
| scoped-test | `python -m pytest tests/<f>.py -k <expr> -q` | exit 0 | no |
| ledger-drift | `python -m pytest tests/test_dormant_ledger_consistency.py -q` | exit 0 (`len(WIRED_LEVER_LEDGER) == ADR-18 count`) | no |
| ruff | `python -m ruff check src tests tools dashboard rl` | exit 0, "All checks passed!" | no |
| mypy | `python -m mypy` (add `tools/ rl/` if touched) | exit 0, "Success" | no |
| loc-delta | `git diff 70e23e5..HEAD --shortstat -- src tests tools dashboard` | cap binds on src+tools+dashboard (tests advisory); net <= 1500 soft / 2250 BLOCK | no |
| ship-gate (static) | `python -m tools.ship_gate_runner all` (= preflight+wipe+loc+ledger+s6.5+inspect-soak; excludes soak S2 + align S4) | exit 0 | no |
| rl-validate | `python -m rl.cli.validate --candidate <c> --baseline <b> --db rl_episodes.db` | exit 0 (EXPERIMENTAL -> advisory) | no |
| rl-criteria | `python -m rl.cli.check_criteria --shadow-db rl_shadow.db --manifests rl_proposals/` | exit 0 = ALL 6 PASS | no |
| path-d-verify | `python tools/path_d_verify.py --json` | exit 0 (lineage clean) / exit 2 drift | no |
| **Tier-3 soak** | `BRIDGE_API_GOV=1 BRIDGE_CYCLE_TIP_SHA=70e23e5 BRIDGE_CYCLE_TYPE=feature BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/ python tools/soak_driver.py --port 8766 --cli-pool-size 2 --total-seconds 1800 --interval-seconds 30` | `Verdict: PASS`, `degrade_count=0` | **YES -- main thread only** |
| **alignment-eval n=6** | `python -m tools.ship_gate_runner align --execute` (resolves `--runs 6`) | ci-gate exit 0 AND adjusted Sonnet pass-rate >= 0.80 | **YES -- main thread only** |

`--cli-pool-size 2` is mandatory; the default 0 silently reproduces the v1.0 cold-start
latency regression (`feedback_soak_cli_pool_flag.md`).

---

## 3. The workflow suite

### Workflow 1 -- `/sm-mvp-audit` (research)

Read-only survey of the SM corpus that hunts MVP-completion gaps and governance-discipline
defects through SM lenses, adversarially verifies each candidate, and emits a single
`MVP-GAP-REPORT.md` whose format is the parseable input contract for `/sm-mvp-converge`.
It NEVER runs a soak or alignment-eval; it READS the newest `reports/soak-*.md` /
`reports/alignment-eval-*.json` as frozen evidence.

```
CYCLE-TIP ANCHOR = 70e23e5 (pinned, read-only)
  Stage 1 CATALOG  13 cataloguers (1 per CORPUS area), parallel, READ-ONLY.
  Stage 2 FIND     12 finders (1 per DIMENSIONS lens), BLIND to each other,
                   loop-until-dry <=3 rounds, quality bar >=2 evidence paths + root cause.
  Stage 3 VERIFY   per candidate: 2 ISOLATED refuters (told to REFUTE) + adjudicator;
                   survives=false only on decisive contradiction.
  Stage 4 REPORT   MAIN THREAD collates survivors into MVP-GAP-REPORT.md (the one write).
```

**CORPUS map (13 read-only cataloguer areas):**

| # | Area | Failure-modes to tag |
|---|---|---|
| C1 | `docs/v*-task-plan.md`, `v*-next-steps.md`, `v*-backlog.md`, `v*-scope.md`, `2026-*-task-list.md` | held-chain-deadlock, stale-DONE, intent-reality-gap, cross-PR-seam-gap, scaffolding-debt |
| C2 | `docs/adr/ADR-*.md` | surface-freeze-violation, dormant-lever, stale-memory, intent-reality-gap |
| C3 | `docs/prompts/**/*.md` | scaffolding-debt, subagent-escape-hatch, long-task-misplacement |
| C4 | `docs/seed-*.md`, `v2.5.1-sonnet-floor-investigation.md`, `v1.3-*-audit.md`, `soak-trigger-matrix.md` | alignment-floor-erosion, held-chain-deadlock, stale-DONE |
| C5 | `docs/jobs/MASTER.md`, `issue-*.md`, `v10-mvp-status.md`, `v10-rl-*.md`, `v10-task-plan.md` | held-chain-deadlock, stale-DONE, intent-reality-gap, surface-freeze-violation |
| C6 | `INTENT.md`, `REQUIREMENTS.md`, `CLAUDE.md`, `MEMORY.md`, `README.md`, `CONTRIBUTING.md`, `smartai.md`, `CHANGELOG.md` | stale-memory, intent-reality-gap, firewall/polarity-leak |
| C7 | `src/stream_manager/**.py` | surface-freeze-violation, dormant-lever, cassette-coverage-gap, code-defect, firewall/polarity-leak |
| C8 | `rl/**.py`, `rl/cli/*.py`, `rl/sources/*.py`, `rl/schema.sql` | firewall/polarity-leak, held-chain-deadlock, stale-DONE, code-defect |
| C9 | `tools/*.py`, `tools/rl_test_helper/**` | dormant-lever, cassette-coverage-gap, self-destructive, firewall/polarity-leak |
| C10 | `tests/**.py`, `tests/cassettes/**`, `beacons/**`, `golden/**`, `fixtures/**`, `conftest.py` | cassette-coverage-gap, self-destructive, stale-DONE, code-defect |
| C11 | `reports/soak-*.md`, `replay-*.md`, `alignment-eval-*.{md,json}`, `poc-*.md` -- **read evidence only** | latency-regression, alignment-floor-erosion, dormant-lever, self-destructive |
| C12 | `$HOME/.claude/projects/C--Users-SeanHoppe-VS-streamManager/memory/*.md` -- **SM-own auto-memory, exact pinned path** | stale-memory, intent-reality-gap, held-chain-deadlock, dead/superseded |
| C13 | `docs/adr/ADR-5*.md` (latency baseline, split out) | latency-regression, intent-reality-gap, stale-memory |

> C12 is pinned to the **exact uppercase canonical** dir (`...-VS-streamManager`, not a
> slug-glob and not lowercase `vs`); the cataloguer resolves `$HOME` and FAILs LOUD if the
> path is absent rather than wandering. Findings from C12 are stamped `scope=local-only /
> non-CI-reproducible` (the auto-memory dir is outside the repo tree). The audit corpus does
> NOT read certPortal session transcripts -- those are a runtime product surface, not an
> audit input (zero-contamination).

**Workflow-tool script skeleton** (corrected agent types -- see section 9 on the registry):

```javascript
export const meta = {
  name: 'sm-mvp-audit',
  description: 'Read-only SM MVP-gap + governance-discipline audit; emits MVP-GAP-REPORT.md. '
    + 'Never runs a soak/alignment-eval; reads existing reports as frozen evidence.',
  phases: [{ title: 'Catalog' }, { title: 'Find' }, { title: 'Verify' }, { title: 'Report' }],
};

const ANCHOR = '70e23e5';                      // PIN: cannot rebaseline
const SAFETY = [
  'READ-ONLY. Read/Glob/Grep/Bash(read-only) only. Never Edit/Write.',
  'FIREWALL: never read/glob/grep **/certPortal/** or C:/Users/SeanHoppe/VS/certPortal/**.',
  'POLARITY: any corpus/ingest read must exclude project_slug IN {streamManager} AND',
  '  session_id == BRIDGE_SM_SELF_SESSION_ID at SQL WHERE (flag post-hoc Python filtering).',
  'LONG-TASK: never run a Tier-3 soak or real claude -p alignment-eval. Read existing reports.',
  'ASCII-only output. Bound Bash to <=90s. Output structured findings only.',
].join('\n');

const CORPUS = [ /* C1..C13 rows above: {id, glob, lenses, readEvidenceOnly?, smInternalMemory?} */ ];
const DIMS   = [ /* F1..F12 from section 4: {id, lens, warStory, scopeAreas} */ ];

// Stage 1: CATALOG -- one read-only cataloguer per area (barrier; finders need the map).
phase('Catalog');
const catalogues = (await parallel(CORPUS.map((a) => () =>
  agent(`${SAFETY}\nCataloguer for ${a.id} (glob: ${a.glob}). Anchor ${ANCHOR}. `
    + `Sort artefacts into kinds, tag failure-modes [${a.lenses}], surface dead/stale files. `
    + (a.readEvidenceOnly ? 'EVIDENCE-ONLY: read existing reports, never trigger a run. ' : '')
    + 'Return per-area inventory + candidate seeds {lens,path,line,symptom}.',
    { label: `catalog:${a.id}`, phase: 'Catalog', agentType: 'Explore', schema: CATALOG_SCHEMA })
))).filter(Boolean);
const seedsByLens = groupSeedsByLens(catalogues);

// Stage 2: FIND -- one BLIND finder per lens, loop-until-dry <=3 rounds (barrier).
phase('Find');
const finds = (await parallel(DIMS.map((d) => () => loopUntilDry(d, seedsByLens[d.lens], 3))))
  .filter(Boolean).flat();

// Stage 3: VERIFY -- 2 isolated refuters + adjudicator per candidate (pipeline, no barrier).
phase('Verify');
const vetted = await pipeline(dedupeById(finds),
  (cand) => parallel([
    () => agent(`${SAFETY}\nRefuter A for ${cand.id}. REFUTE, do not agree. Open ${JSON.stringify(cand.files)} `
      + 'on HEAD. Return CONFIRM(line) | OVERSTATED(what) | REFUTED(contradiction+file:line).',
      { label: `refute:${cand.id}:A`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA }),
    () => agent(`${SAFETY}\nRefuter B for ${cand.id}. ISOLATED from A. Same REFUTE mandate.`,
      { label: `refute:${cand.id}:B`, phase: 'Verify', agentType: 'Explore', schema: VERDICT_SCHEMA }),
  ]),
  (verdicts, cand) => agent(`${SAFETY}\nAdjudicator for ${cand.id}. Verdicts: ${JSON.stringify(verdicts)}. `
    + 'survives=false ONLY on a decisive REFUTED with real file:line. Stamp type (code|process|gate), '
    + 'ADR-18 surface class per file, FR-/NFR-/ADR-rule invariant ID, runnable verify cmd + binary pass.',
    { label: `adjudicate:${cand.id}`, phase: 'Verify', agentType: 'Explore', schema: VETTED_SCHEMA }));

// Stage 4: REPORT -- MAIN THREAD writes MVP-GAP-REPORT.md (returned to main, not a subagent write).
return { survivors: vetted.filter(Boolean).filter((f) => f.survives), anchor: ANCHOR };
```

**`MVP-GAP-REPORT.md` house-style (the input contract).** The report PINS, at the top:
the MVP-scope denominator (scope (a) v10 ledger state with the staleness note; scope (b)
gates: `WIRED_LEVER_LEDGER`=0, last Sonnet pass-rate, last soak p95, `v2.8.0` untagged, and
**current cycle-tip LOC = +1617 already > soft 1500, WARN band, BLOCK 2250, headroom 633**),
the cycle-tip SHA `70e23e5`, and explicit in/out scope (out: certPortal repo, SM-self
governance, freshly running any soak/eval). Each finding is stamped:

```
### FINDING <id>  [type=code|process|gate]  [scope=v10-rl|v1.x-v2.x-main]
- ADR-18 surface class: FROZEN|EVOLVING|EXPERIMENTAL per touched file
- Invariant ID: FR-OG-7 floor 0.80 | NFR-P2 15s | ADR-18 Rule 2/3 | Amendment A/C/D | WIRED_LEVER_LEDGER_COUNT
- Root cause (not symptom): one sentence WHY, >=2 evidence paths (file:line / SHA / PR / Seed-ID)
- files[]: type=code only (ASCII paths); type=process cites prompt/doc/config + violated rule;
           type=gate cites the ship-gate Sn step or the unreachable gate arithmetic
- Verify: <runnable toolchain cmd>     Binary pass: <exit 0 | pass_rate >= 0.80 | tag v2.8.0 prints>
```

A mandatory section 9 carries DD/DV/TR/OQ discipline; **OQ-1** (in-code
`WIRED_LEVER_LEDGER`=0 vs v2.7.1 memory "HOLD 3/0", and `LEDGER_PRODUCTION_EXPECTED=3` at
`ship_gate_runner.py:75`) is surfaced for ship-gate S6, NOT auto-resolved.

---

### Workflow 2 -- `/sm-mvp-converge` (fix + ship)

Consumes `MVP-GAP-REPORT.md` and drives survivor findings to landed, shippable code. Three
terminal dispositions, one per finding type:

- `type=code` -> minimal edit, refute x2, partition-ship via PR.
- `type=process` -> `<id>.proposal.md` artefact, never touches code.
- `type=gate` -> handed BACK to the main thread with a runnable command + binary criterion
  (it needs a soak / real alignment-eval / freeze-lift the workflow is forbidden to run).

```
MVP-GAP-REPORT.md (denominator + cycle-tip pinned)
  SPLIT      parse -> findings; union-find type=code by shared file ->
             file-disjoint partitions (parallel safe); same-file -> serial in one partition.
  FIX&REFUTE per partition in isolation:worktree; minimal edit confined to files[]+tests;
             HARD GUARDS fire here; 2 isolated refuters; <=2-round correction; ship iff unanimous.
  PROPOSALS  type=process -> *.proposal.md (zero code edit).
  GATE       type=gate -> hand to MAIN THREAD (workflow REFUSES to run soak/eval/freeze-lift).
  VERIFY&SHIP only-relevant tests; <=2-round repair; branch fix/sm-mvp-<date>-<tag>;
             stage changed files only; commit citing finding IDs; PR; never main/force-push.
```

**Workflow-tool script skeleton** (union-find + worktree-isolated parallel fixes):

```javascript
export const meta = {
  name: 'sm-mvp-converge',
  description: 'Fix half: union-find partition MVP-GAP-REPORT.md, file-disjoint parallel '
    + 'minimal edits, adversarial refute, targeted tests, PR. Never main/force-push.',
  phases: [{ title: 'Split' }, { title: 'Fix' }, { title: 'Verify+Ship' }],
};

const { code, process: proc, gate, pin } = splitReport('MVP-GAP-REPORT.md'); // pin.cycleTip === '70e23e5'
const partitions = unionFindBySharedFile(code);   // any 2 sharing a file -> same partition

phase('Fix');
// Each partition gets its OWN git worktree so parallel edits cannot collide.
const shipped = await parallel(partitions.map((part) => () =>
  agent(FIX_PROMPT(part, pin), { label: `fix:${part.id}`, phase: 'Fix',
    isolation: 'worktree', agentType: 'general-purpose', schema: PARTITION_SCHEMA })
    .then((r) => refuteLoop(part, r))            // 2 isolated read-only refuters, <=2 rounds
));

// type=process -> proposals (no code). type=gate -> handed back to MAIN THREAD, never run here.
const proposals = proc.map(emitProposalMd);
return {
  shippablePartitions: shipped.filter(Boolean).filter((p) => p.unanimous),
  proposals,
  handToMainThread: gate.map((g) => ({ id: g.id, cmd: g.verify, pass: g.binaryPass,
    runVia: 'run_in_background + ScheduleWakeup', why: 'Tier-3 soak / real align / freeze-lift' })),
  blocked: shipped.filter(Boolean).filter((p) => !p.unanimous),
};
```

**HARD GUARDS (checked at edit time; BLOCK or re-route a partition):**

- **G-FROZEN.** No NEW caller path into a FROZEN seam (`governance.py`, `message_bus.py`,
  `cli_governance.py`, `model_router.py`, `cli_pool`, bus envelope schemas). Bugfix-additive
  (new optional kwarg / enum case / metadata field, no new caller) is permitted; a new
  import/call edge is **re-routed to a `#131`-style freeze-lift `*.proposal.md`** (NOT edited);
  a band/schema reorder is a BLOCK. The reroute is resolved only once the ADR-18 table shows
  the target symbol reclassified EVOLVING (one-way ratchet, operator approval).
- **G-ENVELOPE.** A new bus envelope kind without same-PR `cassette_record.py` +
  `soak_driver.py` extension = BLOCK (`feedback_cassette_must_cover_new_envelopes.md`).
  Detection is a diff-property check: if the diff adds an enum member to
  `envelope_kinds.py`, both cassette files must appear in the same diff.
- **G-LOC.** `git diff 70e23e5..HEAD --shortstat -- src tests tools dashboard`. The cap binds
  on **src+tools+dashboard** (tests + docs advisory). BLOCK at net >= 2250; WARN +
  operator-override at 1500 < net <= 2250; consolidation PASS iff net <= 0.
- **G-FIREWALL.** Concrete grep contract, not a stub: `introduces_certportal_vocab` =
  `rg -i "certportal|JOB-[0-9]|<monitored-role-names>"` over changed files -> any hit = BLOCK;
  `reads_or_writes_certportal_repo` = any path matching `**/certPortal/**` -> BLOCK and surface
  to operator. `is_corpus_ingest_path` without the polarity dual-key exclusion at SQL WHERE = BLOCK.
- **G-LONGTASK.** If a finding's verify is a Tier-3 soak or real alignment-eval, it is
  reclassified `type=gate` and handed to the main thread -- the workflow REFUSES to run it.

**Verify & ship** runs ONLY relevant tests: targeted `pytest -k <touched modules>`,
`ruff check <changed files>`, `mypy` (+`tools/ rl/` if touched), `path_d_verify` for `rl/`
findings, and the envelope/cassette guard if envelopes changed. Plus an **ASCII cp1252
round-trip gate**: every emitted `.md` / `.proposal.md` must satisfy `content.encode('cp1252')`
without `UnicodeEncodeError`. On green: branch `fix/sm-mvp-<date>-<tag>`, stage changed files
only, commit citing finding IDs (ending `Co-Authored-By: Claude Opus 4.8 (1M context)
<noreply@anthropic.com>`), push, open PR. Blocked partitions reported for manual handling.

---

### Workflow 3 -- `/sm-mvp-shipgate` (cycle-close automation)

SM-native; no certPortal analog. Orchestrates S1-S13 as a deterministic pipeline so a cycle
can tag `vN.M.0`. Splits every step into three lanes:

**LANE A -- AUTOMATABLE** (read-only, exit-code-binary, zero `claude -p`, <60s): S0 preflight,
**S0.5 anchor re-pin** (the runner constants are still `CYCLE_TIP_SHA=4902cca` /
`ship/v2.7-p3-ship-gate` -- a stale anchor silently rebaselines LOC, so this is a hard
pre-gate), S1 wipe dry-run, S3 inspect-soak (if a soak report exists), S5 loc, S6 ledger,
**S6-OQ1 ledger reconcile** (mandatory, below), S6.5, S4 align **--dry-run** (resolves
`--runs 6` with zero claude calls), FROZEN surface-class audit (hunk-aware: additive-only =
PASS, new-caller-edge = reroute to #131, reorder = BLOCK), fast-tests, ledger-drift test,
ruff, mypy, regression close-votes (parse EXISTING soak p95 vs Seed v2.4-E 10.156s / v2.4-F 22s).

**LANE B -- MAIN-THREAD-ONLY** (>5min real claude; the workflow EMITS the exact command +
`ScheduleWakeup` handoff, never runs it in a subagent): S2 Tier-3 soak, S4 align --execute
(n=6), conditional S2 cassette refresh.

**LANE C -- OPERATOR-BOUND** (surfaced, never auto-flipped): cycle-type call, S7 ADR-5
append, S9 `git tag -a v2.8.0` (irreversible), S6-OQ1 disposition.

**S6-OQ1 reconcile (closes the green-by-bypass risk).** `WIRED_LEVER_LEDGER={}`
(soak_driver.py:585) + ADR comment 0 agree and the drift test passes, but
`LEDGER_PRODUCTION_EXPECTED=3` (ship_gate_runner.py:75) and v2.7.1 memory claim 3 production
levers -- unverified by any test. Vanilla S6 passes vacuously on the soak-scope 0 while the
production-scope 3 floats. S6-OQ1 reads the soak ledger via **AST** (delegate to the runner's
own `_read_soak_ledger_dict_size()`, never a flat-brace regex -- a populated
`dict[str, tuple[str, int]]` defeats `{[^}]*}`), reads the ADR count, reads
`LEDGER_PRODUCTION_EXPECTED`, reads the production claim from the active close/next-steps doc,
and BLOCKs unless `soak_count == adr_count` AND `prod_expected == prod_claimed` AND
(`prod_expected == soak_count` OR a `docs/v2.8-ledger-reconcile.md` enumerating the 3
production levers exists).

```javascript
// sm-mvp-shipgate lane-A bundle -- runs ONLY read-only checks; maps ANY non-zero to BLOCK.
function verdict(rc, { exit1IsBlock = true } = {}) {        // FIX: non-zero static check = BLOCK, not WARN
  if (rc === 0) return 'PASS';
  if (rc === 2) return 'BLOCK';
  return exit1IsBlock ? 'BLOCK' : 'WARN';
}
const rows = [
  ['S0   preflight',        verdict(sgr('preflight'))],
  ['S0.5 anchor re-pin',    verdict(anchorCheck('70e23e5', 'ship/v2.8-p3-ship-gate'))],  // BLOCK if stale
  ['S1   wipe dry-run',     verdict(sgr('wipe'))],
  ['S5   loc (binding)',    verdict(sgr('loc'), { exit1IsBlock: false })],   // 1500<net<=2250 -> WARN
  ['S6   ledger soak-scope',verdict(sgr('ledger'))],
  ['S6-OQ1 reconcile',      verdict(oq1ReconcileViaAst())],                  // mandatory; AST not regex
  ['S6.5 seed diagnosis',   verdict(sgr('s6.5'))],
  ['S4   align --dry-run',  verdict(sgr('align', '--dry-run'))],
  ['FROZEN surface audit',  verdict(frozenHunkAudit())],                     // hunk-aware
  ['fast-tests',            verdict(run('pytest -m "not slow and not alignment_eval" -q'))],
  ['ledger-drift test',     verdict(run('pytest tests/test_dormant_ledger_consistency.py -q'))],
  ['ruff',                  verdict(run('ruff check src tests tools dashboard rl'))],
  ['mypy',                  verdict(run('mypy'))],
];
return {
  laneA: rows,
  blocked: rows.filter(([, v]) => v === 'BLOCK').map(([n]) => n),
  handToMainThread: [          // LANE B -- main thread fires these, not the workflow
    { step: 'S2 Tier-3 soak',  cmd: SOAK_CMD,  runVia: 'run_in_background + ScheduleWakeup' },
    { step: 'S4 align execute', cmd: 'python -m tools.ship_gate_runner align --execute' },
  ],
  operatorDecisions: ['cycle-type', 'S7 ADR-5 append', 'S9 tag v2.8.0 (irreversible)'],
};
```

After the main thread returns the soak + eval reports, the workflow re-enters for Stage 5
(post-soak adjudicate: re-run S3 inspect-soak + S4 result-parse + regression close-votes;
`FR-OG-7` floor 0.80 is the ship-blocker -- align exit 2 folds a `vN.M.1` corrective sub-phase
per the v1.3.1 / v2.5.1 / v2.7.1 precedent). EXPERIMENTAL `rl/` failures CANNOT block this
main-cycle ship-gate.

---

## 4. SM DIMENSIONS -- finder lens catalog

The SM swap-point. One blind finder per lens, coverage by-kind not by-luck, quality bar
>=2 evidence paths + root cause.

| Lens | What the finder greps/reads | Real SM incident it would have caught |
|---|---|---|
| **held-chain-deadlock** | Seed/phase/issue carried N consecutive cycles on an unmet dependency; confirm structural-unreachability via gate arithmetic (`n_actual` vs `n_required`, CI floor vs cap). | v10 P5 deferred 4 cycles on Seed v2.6-C; gate unreachable (`n_actual=79/200`, off-arm CI ~0.43 >> 0.10 cap, #177); Amendment D split the gate. |
| **dormant-lever** | `WIRED_LEVER_LEDGER` dict (currently `{}`) vs ADR-18 `WIRED_LEVER_LEDGER_COUNT` comment vs `LEDGER_PRODUCTION_EXPECTED=3` vs close-memory "HOLD 3/0"; soak "fire rate = 0%". | OQ-1 ledger drift; Haiku fastpath wired-but-unused v1.7->v1.9, DORMANT-3, force-ripped v2.0 P3. |
| **surface-freeze-violation** | New caller path / reorder / non-additive change into a FROZEN module; RL reaching a FROZEN gov symbol. | ADR-18 minted after v1.7->v1.9 +2800 LOC on unfired FROZEN-seam levers; #131 gated on `model_router.route` reclass. |
| **alignment-floor-erosion** | Sonnet/Haiku pass_rate in [0.80, 0.85] at n<6; n=6 escape-hatch not fired. | v2.5 P2 BLOCK at Sonnet 0.7895 n=3; re-measured n=6 -> 0.9375 (artefact). Drove the n=6 mandate. |
| **cassette-coverage-gap** | New bus envelope kind in src without same-PR `cassette_record.py` + `soak_driver.py`; beacon/cassette desync. | v1.3 Learn Mode nearly tagged without LM coverage; v1.3.0 re-shipped as v1.3.1. |
| **stale-memory / intent-reality-gap** | MEMORY/INTENT/REQUIREMENTS/ADR posture contradicted by code; FR-* with no enforcing symbol; "DONE/RESOLVED" the source falsifies. | `v10-mvp-status.md` still says P5 "0% BLOCKED 4th deferral" despite #214 landing P5 (24/24 green); FR-OG-7 silently degrades on fresh clone (`.sm-context.yaml` gitignored). |
| **cross-PR-seam-gap** | Writer emits an envelope no consumer reads / reader expects a field no writer populates; only one end of a designed seam landed. | `feedback_cross_pr_seam_review.md`: feature branch reached main with one seam end; subagent reported "all clean" over a silent revert. |
| **firewall/polarity-leak** | certPortal vocab/paths/JOB-IDs/roles in SM source; corpus/ingest path missing the polarity dual-key exclusion. | `feedback_no_self_monitor.md` (polarity-flip); `feedback_certportal_dev_firewall.md` + zero-contamination. |
| **latency-regression** | Soak overall p95 > Seed v2.4-E 10.156s; L4 p95 > v2.4-F 22s; ADR-5 ceiling 15s -- from EXISTING reports, no re-run. | v2.7.1 overall p95 10.480s breached v2.4-E; L4 22.49s tripped v2.4-F. v1.1 cold-start misattributed to the hydrator. |
| **self-destructive (green-by-bypass)** | `--cli-pool-size 0` default, PATHSPEC-UNSET passing the LOC gate vacuously, stale-fixture soak, glob-narrowing no-op, tautological assert. | PR #184 narrowed `soak-*.md`->`soak-tmp-*.md` but driver writes `soak-{iso_ts}.md` (no-op); default `--cli-pool-size 0` reproduces cold-start. |
| **scaffolding-debt / subagent-escape-hatch** | Unbound `[ ]` decision boxes, "deferred to a follow-up", TODO stubs, empty MEMORY.md sections; an orchestration prompt scheduling a >5min task in a fan-out subagent. | `feedback_subagent_escape_hatches.md`; `feedback_subagent_long_task_abandonment.md`. |
| **code-defect (off-band / latency-path)** | A concrete logic bug not covered above: off-by-band helper, latency-path regression, deterministic-Python trainer leaking an LLM call. | `feedback_cycle_tolerance_masks_bugs.md` (off-by-bucket helper bug masked by feature-cycle LOC tolerance). |

**certPortal -> SM lens mapping:** rework-loop + stall -> held-chain-deadlock; stale-DONE +
intent-reality-gap -> stale-memory/intent-reality-gap; self-destructive keeps its name;
scaffolding-debt gains the SM escape-hatch arm; code-defect is largely subsumed by
latency-regression + the freeze/cassette lenses. The six SM-native additions (dormant-lever,
surface-freeze-violation, alignment-floor-erosion, cassette-coverage-gap, cross-PR-seam-gap,
firewall/polarity-leak) police SM-only invariants and are the reusable swap-point.

---

## 5. Hard-constraint guardrails (HOUSE_STYLE swap point)

Every workflow + every fan-out subagent prompt encodes these twelve guards verbatim.

- **G1 certPortal dev-firewall.** No stage reads `**/certPortal/**`. Enforced by
  `.claude/settings.local.json` deny patterns; a fired deny is surfaced, never worked around.
  Runtime JSONL-tail of certPortal sessions is the product and is unaffected (dev-session boundary only).
- **G2 polarity-flip self-monitor exclusion.** Any corpus/replay/ingest/OPE/training path
  INCLUDES a row iff `project_slug NOT IN STREAM_MANAGER_PROJECT_SLUGS (default {streamManager},
  env BRIDGE_SM_PROJECT_SLUGS) AND session_id != BRIDGE_SM_SELF_SESSION_ID`. Real enforcement is
  three-tier: (1) write-time refusal on project_slug in `episode_logger` (acceptable), (2) the
  SQL WHERE dual-key default-exclude, (3) `test_audit_self_monitor_hardguard.py`. A self-session
  row in `rl_episodes.db` / `rl_shadow.db` is a FAIL, not a warning.
- **G3 ADR-18 surface freeze.** FROZEN edits are additive-only, no new caller paths, no
  reorder. FROZEN->EVOLVING is a one-way ratchet via the #131 freeze-lift cycle frame
  (`model_router.route` gates #124/#125). Reviewers diff PR head vs cycle-tip on the four seam files.
- **G4 DORMANT-N + load-bearing ledger comment.** Wired lever 0% fire across 2 soaks =
  DORMANT-2 (WARN); 3 = DORMANT-3 (BLOCK, must revive or rip). `WIRED_LEVER_LEDGER_COUNT`
  comment is test-asserted against the soak_driver dict; OQ-1 surfaces to S6, never auto-resolved.
- **G5 LOC budget at cycle-tip anchor.** `git diff 70e23e5..HEAD --stat -- src tests tools
  dashboard`; cap binds on src+tools+dashboard, tests+docs advisory; consolidation <=0,
  feature 1500 soft / 2250 BLOCK; predecessor-tag diff is narrative-only (Amendment C).
- **G6 cassette-coverage same-PR rule.** A new envelope kind extends `cassette_record.py` +
  `soak_driver.py` in the same PR or BLOCK.
- **G7 LONG-TASK main-thread-only (reshapes the workflow).** Tier-3 soak / real alignment-eval
  / shadow A/B run from the main thread via `run_in_background` + `ScheduleWakeup`, NEVER in a
  fan-out subagent. Gate-type findings are emitted as composed argv + binary criterion and
  handed back; fan-out subagents stay read-only and <=90s.
- **G8 n=6 alignment-eval near floor.** `--runs 6` when prior-cycle Sonnet pass_rate within
  0.05 of the FR-OG-7 0.80 floor (or instability triggers). 3-run majority is too noisy
  (the v2.5 P2 0.7895 BLOCK lesson).
- **G9 robin owns v10 RL verification.** Every v10 P1-P5 verdict (OPE roll-ups, shadow
  ship-criteria, DORMANT reads) routes to `robin`, read-only, never relaxing pre-registered
  criteria, never launching the soak. EXPERIMENTAL findings cannot block the main ship-gate.
- **G10 reviewer-cannot-execute + per-agent independent governance.** Refuter subagents are
  read-only by contract (no Write/Edit, no long task); the workflow never gates one agent on
  another's completion state.
- **G11 ASCII-only (cp1252).** No smart quotes, em-dashes (`--`), box-drawing, or section-sign;
  emitted files pass a `content.encode('cp1252')` round-trip gate.
- **G12 goal-reviewer self-dispatch.** The FIRST action of any `/goal`-driven fire is
  `Agent(subagent_type=goal-reviewer, prompt=<directive verbatim>)`; PASS proceed / FLAG
  surface to Sean / REFUSE halt. No mutating stage dispatches until a PASS/operator-cleared verdict.

**Why these matter for an autonomous MVP-100 drive.** The drive is mostly long-task + gate
work -- exactly where an unguarded loop self-destructs. G1/G2/G11 keep the corpus
uncontaminated so the alignment-eval and RL-episode signals that GATE the MVP stay
trustworthy. G3/G5/G6 stop the drive buying progress with surface it cannot pay for.
G4/G8 are the falsification spine. G7/G9/G10/G12 are the orchestration spine: long tasks
return to the main thread, v10 verdicts go to robin, refuters stay read-only, goal-reviewer
pre-clears every fire. Together they make MVP-100 progress auditable and reversible rather
than fast-and-fragile.

---

## 6. Compensating for the soak bottleneck (`/sm-mvp-shadow-synth`)

> The user steer: *think outside-the-lines to compensate for lack of soak.*

**The bottleneck.** Closing #112 (the gate to v10 100%) requires 3 consecutive Tier-3 shadow
soaks producing real `(production, candidate, state, ground-truth)` tuples + all 6
pre-registered ship criteria PASS. A Tier-3 soak is >5min, main-thread-only, needs a live
non-SM Claude CLI session (certPortal at runtime), and is fragile (OQ-2: last overnight soak
read `LM p95 = 5593.95 s`, almost certainly a single un-killed CLI dispatch; OQ-1: lever
ledger read 0). This is the autonomy ceiling -- a workflow cannot run a soak.

**The key insight:** the entire v10 design is *off-policy* ("trained on logged Tier-3 +
cassette + golden + probe episodes"), and ADR-18 Amendment D already carved a **v10.1-mode
infra-validation path** (baseline-vs-baseline shadow run, `soak_run_id` suffix `--mode=v10.1`,
excluded from v10.3 writeback promotion). That means most of the shadow harness can be
exercised end-to-end on *existing data*, in-workflow, in seconds -- the live soak is only
strictly required for the genuine on-policy promotion evidence.

`/sm-mvp-shadow-synth` produces six classes of soak-substitute evidence, all offline,
firewall- and polarity-clean, no live session, no `claude -p`:

1. **OPE-first offline evaluation.** Run `rl/ope.py` + `rl/validate.py` (the 5-stage gauntlet)
   against the existing **608-episode `rl_episodes.db`**: IPS/DR estimates of candidate-vs-baseline
   reward, HITL agreement, and FR-OG-7 violation count -- computed off-policy, no new soak.
   `python -m rl.cli.validate --candidate <c> --baseline <b> --db rl_episodes.db`. This is the
   designed mechanism; it substitutes for the shadow on everything except true on-policy divergence.
2. **Cassette-replay shadow.** Drive `rl/shadow.py` ShadowRecorder from `tools/cassette_replay.py`
   instead of a live soak: replay recorded bus envelopes through `bus.subscribe_decision` ->
   ShadowRecorder writes `rl_shadow.db` tuples in seconds, deterministic, in-process. Tag
   `--mode=v10.1`. Then `python -m rl.cli.check_criteria --shadow-db rl_shadow.db --manifests
   rl_proposals/` exercises all 6 criteria end-to-end -- proves the harness + closes the
   INFRASTRUCTURE side of #112.
3. **Synthetic-fixture (Path-D) replay.** #214 landed exactly this: `tools/path_d_verify.py` +
   the synthetic fixture deterministically generate shadow tuples. Running `check_criteria`
   against the fixture is a CI-repeatable end-to-end criteria evaluation, fully offline.
4. **Bootstrap / block-resampling windows.** To approximate the "3 consecutive shadow windows"
   statistic from the single corpus: partition the 608 episodes into 3 temporal blocks (or
   block-bootstrap resample), run `check_criteria` per block, require all 3 PASS. This is an
   ADVISORY confidence proxy that **de-risks before** a real soak; it is NOT a pre-registration
   satisfier.
5. **Micro-soak tier (new ADR-17 tier).** A cassette-fed end-to-end bus run that completes in
   seconds, in-subagent-safe, giving a fast regression canary between rare real Tier-3s. New
   tier in ADR-17; not a promotion vehicle.
6. **Cassette-replay alignment proxy.** The alignment-pass-rate ship criterion normally needs
   real `claude -p` n=6 (>5min, main thread). Use recorded alignment cassettes
   (`tests/cassettes/`, `tools/cassette_replay.py`) to compute a fast pass-rate PROXY in-workflow.
   Caveat: catches regression vs the recorded baseline only, not live model drift; the real n=6
   still gates the actual ship. But the proxy flags a regression before the human spends the real eval.

**The integrity firewall (this is what keeps it honest).** The pre-registered ship criteria
are NOT relaxed based on observed data (design section 9, p-hacking guard). So the evidence is
split into two ledgers that never mix:

| Ledger | Vehicles | What it advances | What it CANNOT do |
|---|---|---|---|
| **Infra-validation / regression** | OPE, cassette-shadow, synthetic-fixture, bootstrap, micro-soak, cassette-align proxy | Closes the infrastructure/feasibility side of #112; de-risks; adds `is_ready_for_shadow_v10_1()`; tagged `--mode=v10.1` | Count toward v10.3 writeback promotion (Amendment D ignores `--mode=v10.1` rows) |
| **Promotion** | Real 3x Tier-3 live shadow soak + real n=6 alignment-eval (main thread, human-gated) | Satisfies the 6 pre-registered v10.3 ship criteria | -- (the only evidence that does) |

So `/sm-mvp-shadow-synth` lets the autonomous suite take #112 from "infra landed, untested"
to "infra validated end-to-end + feasibility-positive + regression-clean + entry-gate predicate
added", leaving ONLY the irreducible real-data soak as the main-thread remainder. It maximizes
unattended progress without touching the pre-registration discipline.

```javascript
export const meta = {
  name: 'sm-mvp-shadow-synth',
  description: 'Soak-substitute: OPE + cassette-shadow + synthetic-fixture + bootstrap + '
    + 'micro-soak + cassette-align proxy. Offline, --mode=v10.1 infra-validation only. '
    + 'NEVER satisfies pre-registered v10.3 ship criteria (real Tier-3 soak does).',
  phases: [{ title: 'OPE' }, { title: 'Shadow-replay' }, { title: 'Bootstrap' }, { title: 'Verdict' }],
};
// All stages READ rl_episodes.db (polarity-excluded), replay cassettes, write rl_shadow.db
// with soak_run_id '--mode=v10.1'. robin (G9) owns the final ship-criteria read.
// Returns { infraValidation: {...}, regressionClean: bool, feasibility: {...},
//           STILL_NEEDS: '3x real Tier-3 shadow soak + real n=6 align (main thread)' }.
```

---

## 7. End-to-end MVP-100 drive sequence

The four workflows compose into the actual drive. Main thread stays in the loop; long tasks
and the tag stay main-thread / operator.

1. **`/sm-mvp-audit`** -> `MVP-GAP-REPORT.md` (staleness of `v10-mvp-status.md`, OQ-1 ledger,
   `is_ready_for_shadow_v10_1()` gap, v2.8 P2 env-split not started, etc.).
2. **`/sm-mvp-converge`** -> lands the `type=code` fixes (refresh the ledger doc; add the
   v10.1 entry-gate predicate; v2.8 P2 env-split `BRIDGE_CLI_TIMEOUT`/`_EVAL`); emits
   `type=process` proposals (memory updates); hands `type=gate` items back.
3. **`/sm-mvp-shadow-synth`** -> off-policy + cassette-shadow infra-validation closes the
   harness side of #112 and de-risks the real soak.
4. **`/sm-mvp-shipgate`** -> lane-A static verification green; main thread fires the
   **Tier-3 soak** + **n=6 alignment-eval** via `run_in_background` + `ScheduleWakeup`;
   post-soak adjudicate; operator tags **v2.8.0**.
5. **#112 close** -> main thread runs the 3x real Tier-3 shadow soak (the irreducible step);
   `rl.cli.check_criteria` exit 0; close #112.
6. **#131 freeze-lift lane** (explicit gate finding class `freeze-lift-request`): the audit
   emits the `model_router.route` FROZEN->EVOLVING reclassification proposal + the operator
   one-way-ratchet decision; on approval, mint `docs/prompts/v10x-orchestration/phase-0-cycle-frame.md`.
7. **#124 + #125** -> once #131 reclassifies the seam: wire `BRIDGE_L4_FALLBACK_CONFIDENCE` +
   un-ADVISORY OPE stage-1 (#124); restore Ridge-Q DR estimator (#125). v10 MVP -> 100%.

The only steps a workflow cannot do autonomously: the real Tier-3 soaks (steps 4-5), the
real n=6 alignment-eval (step 4), and the operator-bound `model_router.route` reclassification
(step 6) and `v2.8.0` tag (step 4). Everything else the suite drives.

---

## 8. What this is NOT allowed to do (refusals, restated)

- Read or edit anything under `**/certPortal/**` (firewall) -- including spawning a subagent
  to triage certPortal issues. Surface to operator instead.
- Govern / monitor an SM-own session (polarity-flip). Self-session rows are a loud FAIL.
- Add a new caller path into a FROZEN seam without an approved #131 freeze-lift.
- Run a Tier-3 soak or real alignment-eval inside any fan-out subagent.
- Relax a pre-registered v10.3 ship criterion based on observed/synthetic data.
- Auto-tag, auto-flip an operator decision box, or commit to `main` / force-push / skip hooks.

---

## 9. Adversarial-review fixes folded in

The drafting workflow ran 4 adversarial reviewers (firewall/polarity, ADR-18, long-task,
fidelity/MVP-reach). Their BLOCKER/MAJOR findings are corrected above:

| Severity | Finding | Fix applied |
|---|---|---|
| BLOCKER | Draft scripts hard-coded `subagent_type: "cavecrew-*"`, which are not in repo `.claude/agents/` | Use `agentType: 'Explore'` for read-only catalog/find/refute; route specialized lenses to real project agents (`firewall-auditor`, `governance-trace-verifier`, `robin`, `goal-reviewer`). See section 10. |
| BLOCKER | Firewall carve-out + C12 slug-glob could wander; wrong casing (`vs` vs `VS`) | C12 pinned to exact uppercase `...-VS-streamManager/memory/`, fail-loud, `scope=local-only`; audit corpus excludes certPortal transcripts. |
| BLOCKER | `path_to_100` missing the #131 freeze-lift lane | Added explicit `freeze-lift-request` gate-finding class + operator one-way-ratchet step (section 7 step 6). |
| BLOCKER | Lane-A static rows used `.returncode and 1` -> `_verdict(1)` = WARN not BLOCK | `verdict(rc, {exit1IsBlock:true})` maps any non-zero static-check to BLOCK. |
| MAJOR | S6-OQ1 ledger regex `{[^}]*}` cannot parse a populated nested dict | Delegate to `ship_gate_runner._read_soak_ledger_dict_size()` (AST), never a flat-brace regex. |
| MAJOR | LOC bucket text said "src+tools+dashboard" but pathspec included tests | Clarified: diff reports all four; the BLOCK gate binds on src+tools+dashboard, tests+docs advisory. |
| MAJOR | GUARD firewall predicates were undefined stubs | Replaced with a concrete `rg -i` contract citing the deny patterns. |
| MAJOR | Current HEAD already +1617 > soft 1500 not surfaced | Surfaced in the report denominator pin (WARN band, headroom 633 to BLOCK). |
| MAJOR | Polarity attestation oversimplified to "SQL WHERE not Python" | Rewritten as the real three-tier enforcement (write-time refusal + SQL WHERE dual-key + hardguard test). |
| MINOR | ASCII cp1252 handling, FROZEN audit hunk-awareness, freeze-lift honored-gate, S0.5 short-circuit | Added cp1252 round-trip gate, hunk-aware FROZEN audit, honored-gate check, S0.5 hard pre-gate. |

---

## 10. How to actually run these

These are proposals, not yet wired. To run any of them via the Workflow tool, the main thread
invokes `Workflow({ script: <the JS above> })` (ultracode / explicit opt-in only). Notes:

- **Agent registry.** The repo `.claude/agents/` provides `goal-reviewer`, `robin`,
  `firewall-auditor`, `governance-trace-verifier`, `session-target-scout`, `poc-watch`,
  `poc-coordinator`, and the POC probers -- plus generic `Explore` / `general-purpose`. The
  caveman plugin's `cavecrew-investigator` / `-builder` / `-reviewer` are available only via
  the plugin namespace (`caveman:cavecrew-investigator`); prefer the in-repo agents + `Explore`
  for portability.
- **Long tasks stay on the main thread.** Workflows return a `handToMainThread` list; the main
  thread fires each via `Bash(run_in_background)` + `ScheduleWakeup` and re-enters the workflow
  (or its post-soak stage) on wakeup. Never put a soak/eval inside `agent()`.
- **goal-reviewer first.** If a workflow is fired from a `/goal` directive, dispatch
  `goal-reviewer` before any mutating stage (G12).
- **Suggested file homes** (when wired): `.claude/workflows/sm-mvp-audit.js`,
  `sm-mvp-converge.js`, `sm-mvp-shipgate.js`, `sm-mvp-shadow-synth.js`; the lane-A static
  bundle of W3 can also live as a plain `tools/` script delegating to `ship_gate_runner.py`.

---

## 11. Open questions for the operator

- **OQ-A.** Should `/sm-mvp-shadow-synth` infra-validation evidence be allowed to *close* the
  infrastructure side of #112 (with the real soak tracked as a separate promotion gate), or
  must #112 stay fully OPEN until the 3x real Tier-3 soak? (Proposal: split #112 into
  #112-infra / #112-promotion to make the autonomous progress legible.)
- **OQ-B.** Is the `model_router.route` FROZEN->EVOLVING reclassification (#131) pre-authorized
  once #112 + the trigger conditions hold, or does each freeze-lift need a fresh operator sign-off?
- **OQ-C.** OQ-1 disposition: are there genuinely 3 production levers (reconcile artefact
  enumerating wire-SHAs + DORMANT status), or should `LEDGER_PRODUCTION_EXPECTED` / the v2.7.1
  memory be corrected to 0? S6-OQ1 BLOCKs until this is resolved.
- **OQ-D.** Wire all four workflows now, or start with `/sm-mvp-audit` (lowest-risk, read-only)
  and validate its `MVP-GAP-REPORT.md` output before building the fix/ship/shadow lanes?

---

## 12. References

- Aspirational: `Claude-ResearchFixWorkflow.md`.
- MVP anchor: `docs/v10-mvp-status.md` (stale at P5; refresh is finding #1).
- Gauge discipline: `docs/2026-05-22-guage-notes.md` (DD/DV/TR/OQ; schedule-estimator framing).
- Governance: `INTENT.md`, `REQUIREMENTS.md` (FR-OG-7, NFR-P2, FR-PPP), `CLAUDE.md` (firewall,
  polarity, long-task, robin).
- ADR-18 (`docs/adr/ADR-18-mvp-surface-freeze.md`): surface freeze, Rules 1-6, Amendments A/C/D.
- Toolchain: `tools/ship_gate_runner.py`, `soak_driver.py`, `alignment_eval.py`,
  `path_d_verify.py`, `cassette_record.py`, `cassette_replay.py`; `rl/cli/{train,validate,
  check_criteria,shadow}.py`, `rl/{ope,shadow,stop_conditions,bandit}.py`.
- v2.8 fire ledger: `docs/v2.8-next-steps.md`, `docs/v2.8-task-plan.md`.
- Memory war-stories cited per-lens in section 4.
