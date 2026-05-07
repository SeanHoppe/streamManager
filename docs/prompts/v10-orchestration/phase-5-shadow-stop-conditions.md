You are implementing **Phase P5 — Shadow A/B harness + ship-criteria codification (v10.2)** for the streamManager v10 RL companion track.

## Branch + base

- Base: `main` with v10 P1 + P2 + P3 + P4 merged.
- PR target: `main`.
- Branch: `feat/v10-shadow-stop` (or operator's choice).
- If P4 trainer has not produced ≥ 1 proposal manifest with `is_ready_for_shadow()=True`, ABORT (no candidate to shadow yet).

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P5 must touch ONLY:

- `rl/shadow.py` — new module; ghost-path candidate execution alongside production decision.
- `rl/cli/shadow.py` — new CLI: `python -m rl.cli.shadow --proposal <json> --soak-tier 3`.
- `rl/stop_conditions.py` — new module; pre-registered v10 ship-criteria checks.
- `tests/test_rl_shadow.py`, `tests/test_rl_stop_conditions.py` — new test files.
- `docs/v10-rl-design.md` — APPEND a §"v10 ship criteria — pre-registered" subsection ONLY (additive doc edit).

NO edits to gov code. Shadow path is non-invasive: it RECEIVES the production decision via bus subscription, runs the candidate policy in-process for the same input, records (production_decision, candidate_decision, shared_state, ground-truth-when-available) to a separate `rl_shadow.db`, but NEVER affects the production decision flow.

Pre-flight grep:

```
grep -nE 'governance_decision|RoutingDecision|requires_alignment' src/stream_manager/governance.py src/stream_manager/cli_governance.py
```

Verify FROZEN symbols still present.

## Task brief

Per the v10 design review §"Issue #4 — Stop conditions" and §"Validation stage 5", v10.2 adds a shadow A/B harness that runs candidate policies in a ghost path during real Tier 3 soaks, plus a codified ship-criteria checker that decides when v10.3 (writeback authority) may be greenlit.

Shadow runs MUST NOT affect production decisions. Production decision is final; shadow records what the candidate WOULD have decided.

### Ship criteria — pre-registered (DO NOT change at evaluation time)

| Criterion | Threshold | Window |
|---|---|---|
| Shadow reward improvement | reward(candidate) ≥ reward(baseline) + 0.02 | 3 consecutive Tier 3 shadows |
| FR-OG-7 violations | 0 | every shadow (full alignment-golden + adversarial) |
| HITL agreement | ≥ baseline − 2 % absolute | every shadow |
| Alignment-eval pass rate | ≥ baseline pass rate | every shadow |
| Posterior CI on best arm | ≤ 0.10 | computed at retrain |
| Parameter drift between retrains | |Δθ| ≤ 0.02 | 3 consecutive retrains |

Pre-registered means: pick once, before data collection, and write into the formal design doc (per §"v10 ship criteria — pre-registered" addition). Do NOT relax thresholds based on observed data — that's p-hacking.

### Deliverables

1. **`rl/shadow.py`** — ghost-path execution:

   - `class ShadowRecorder`:
     - `__init__(self, candidate: Candidate, db_path: Path)` — opens `rl_shadow.db` (WAL, dedicated writer, separate from `rl_episodes.db`).
     - `on_governance_decision(envelope: dict) -> None` — bus callback. Computes the candidate's would-be decision in-process (offline path, NOT a real `claude -p` call), writes (production, candidate, state, ground-truth-if-known) to `rl_shadow.db`.
   - `class ShadowSchema`:
     ```sql
     CREATE TABLE shadow_episodes (
         shadow_id           INTEGER PRIMARY KEY AUTOINCREMENT,
         ts_utc              TEXT NOT NULL,
         session_id          TEXT NOT NULL,
         trace_id            TEXT NOT NULL,
         state_features_json TEXT NOT NULL,
         production_action   REAL NOT NULL,
         production_verdict  TEXT NOT NULL,
         candidate_action    REAL NOT NULL,
         candidate_verdict   TEXT NOT NULL,
         agree               INTEGER NOT NULL, -- 0/1
         ground_truth_known  INTEGER NOT NULL, -- 0/1
         ground_truth_verdict TEXT,           -- nullable
         soak_run_id         TEXT NOT NULL,   -- groups shadow runs to soak runs
         UNIQUE(session_id, trace_id, soak_run_id)
     );
     PRAGMA journal_mode=WAL;
     ```

   - **Non-invasion invariant**: `on_governance_decision` MUST be wall-clock-bounded (≤ 50 ms p95; budget cited from ADR-5 §"v10 shadow overhead", to be added when P5 lands) and MUST NOT block the bus. If candidate evaluation exceeds budget, drop the shadow record and emit `rl_shadow_dropped` envelope. Production NEVER waits on shadow.

2. **`rl/stop_conditions.py`** — pre-registered ship-criteria checker:

   - `@dataclass class ShipCriteria` — frozen thresholds (numbers from the table above; values hard-coded, not configurable).
   - `evaluate_criteria(shadow_db: Path, manifest_dir: Path, baseline: Candidate) -> CriteriaReport`:
     - Reads last 3 shadow runs.
     - Reads last 3 manifests.
     - Computes each criterion.
     - Returns report with one PASS / FAIL per criterion + overall verdict.
   - All-criteria-PASS = signal that v10.3 writeback can be opened (a separate human-gated review, NOT auto-promotion).

3. **`rl/cli/shadow.py`** — CLI: `python -m rl.cli.shadow --proposal rl_proposals/<UTC>Z.json --soak-tier 3 [--soak-args "..."]`:
   - Spawns `tools/soak_driver.py --cli-pool-size 2 --shadow-recorder rl_shadow.db [--shadow-proposal <path>]` as a subprocess.
   - The `--shadow-recorder` flag is a NEW soak_driver CLI surface (added in P5 OR a P5 predecessor sub-phase IF soak_driver is FROZEN). The soak driver, running in-process with the bus, invokes `rl.shadow.ShadowRecorder.on_governance_decision` for each envelope.
   - **Open question for P0**: if `tools/soak_driver.py` is on the FROZEN list (per ADR-18), P5 cannot add a CLI flag. In that case shadow recording must use a sidecar JSONL-tail strategy (read soak's bus log file as it appends), with the recorder written to `rl_shadow.db` post-run, NOT live. Resolve this in P0 formal design before P5 merge.
   - Records shadow episodes to `rl_shadow.db` with `soak_run_id = <soak start UTC>`.
   - On soak completion: writes `reports/v10-shadow-<UTC>Z.md` summarising agreement rate, candidate-vs-production reward, FR-OG-7 row outcomes, HITL agreement.

4. **`rl/cli/check_criteria.py`** — CLI: `python -m rl.cli.check_criteria --shadow-db rl_shadow.db --manifests rl_proposals/`:
   - Runs `evaluate_criteria(...)`.
   - Writes `reports/v10-criteria-<UTC>Z.md`.
   - Exit code 0 = ALL PASS (writeback can be opened); 1 = at least one FAIL.

5. **Tests** — `tests/test_rl_shadow.py`:
   - `test_shadow_does_not_block_bus` — `on_governance_decision` returns within 50 ms p95 over 1000 synthetic envelopes.
   - `test_shadow_records_disagreement` — production verdict ≠ candidate verdict → row inserted with `agree=0`.
   - `test_shadow_drops_on_overrun` — synthetic candidate that takes 200 ms is dropped + warning emitted.
   - `test_shadow_isolated_db` — shadow writes go to `rl_shadow.db`, not `rl_episodes.db`.
   - `test_shadow_unique_constraint` — same `(session_id, trace_id, soak_run_id)` triple → IntegrityError.
   - `test_shadow_no_self_monitor` — envelopes from SM's own session ID dropped (memory: `feedback_no_self_monitor.md`).

6. **Tests** — `tests/test_rl_stop_conditions.py`:
   - `test_all_criteria_pass_returns_pass` — fixture data engineered to satisfy all 6 → overall PASS.
   - `test_fr_og_7_failure_overrides_other_passes` — single FR-OG-7 violation → overall FAIL even if rest pass.
   - `test_hitl_below_floor_fails` — HITL agreement < baseline − 0.02 → FAIL.
   - `test_two_consecutive_shadows_insufficient` — n=2 instead of 3 → FAIL with "insufficient shadow runs" message.
   - `test_parameter_drift_too_high_fails` — |Δθ| > 0.02 across 3 retrains → FAIL.
   - `test_thresholds_are_constants_not_env_overrides` — assert that no threshold is read from env var (pre-registration discipline).

7. **`docs/v10-rl-design.md` append** — new subsection §"v10 ship criteria — pre-registered" containing the criteria table verbatim, plus prose: "These thresholds are pre-registered. They are NOT relaxed based on observed data. If criteria cannot be met after 3 retrains × 3 shadows, the v10 track enters DORMANT-N per ADR-18 Rule 2 and is reviewed for rip in the next ship cycle."

### Shadow-only invariant

P5 changes NO production behaviour. Verify:

- `cli_dispatch_ms` p95 unchanged vs P4 in a Tier 3 soak with shadow active.
- Production verdicts in shadow runs are byte-identical to a shadow-disabled baseline soak (recorded in pre-merge sanity check).
- All v1.7–v2.0 + v10 P1–P4 tests green.

### LOC budget

P5 net add ≤ 600 lines. Shadow recorder + criteria checker + CLIs are all small; tests dominate.

## DOD

- [ ] `rl/{shadow,stop_conditions}.py` + `rl/cli/{shadow,check_criteria}.py` created
- [ ] `tests/test_rl_{shadow,stop_conditions}.py` created
- [ ] `docs/v10-rl-design.md` §"v10 ship criteria — pre-registered" appended
- [ ] Shadow path NEVER blocks production; tests cover the non-invasion invariant
- [ ] Pre-registered thresholds are CODE CONSTANTS, not env-overridable; test asserts this
- [ ] Sample shadow report attached to PR, from a real Tier 3 soak with the latest P4 proposal
- [ ] Sample criteria report attached to PR (expected outcome at first run: FAIL on "insufficient shadow runs")
- [ ] LOC budget ≤ 600 net add
- [ ] All v1.7–v2.0 + v10 P1–P4 tests green
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `feat(rl):`

Report back when PR is open with: PR URL, diff stat, file list, shadow-soak report path, criteria-check report path, post-P5 production-verdict-byte-identity confirmation.

## v10.3 writeback note

P5 enables but does NOT enact writeback. v10.3 (lifting `bias_consult` from advisory to threshold-write authority) requires a SEPARATE explicit ADR-18 amendment + its own phase prompt, gated by `evaluate_criteria` returning ALL PASS for ≥ 1 cycle without manual override. Do NOT write the v10.3 amendment in P5 — it lives in a future phase prompt.
