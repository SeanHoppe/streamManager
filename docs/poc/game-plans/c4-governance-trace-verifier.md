# C4 — `governance-trace-verifier` game plan

**Agent file:** `.claude/agents/governance-trace-verifier.md`
**Role:** Governance-trace prober.
**Tools:** Read, Grep, Bash.

## Role in fleet

Takes one C3 envelope → confirms governance produced a decision row with verdict band + bias provenance + (per INTENT) alignment+cadence signal + (per INTENT §"Sub-agent governance principles") role-bound divergence.

## Inputs

- C3's `envelope_id` + `source_slug`.
- `src/stream_manager/governance.py` (FROZEN; read-only).
- `src/stream_manager/agent_registry.py` (read-only).
- Bus DB (read-only).
- INTENT.md §"Plan alignment + cadence", §"Sub-agent governance principles".

## Steps

1. Query `decisions` for the envelope_id; confirm row exists with verdict, band, confidence, metadata.
2. Query `decision_suggestions` for the decision_id; record bias provenance.
3. Parse decision `metadata_json`; record whether `alignment_score` + `cadence_band` are present.
4. Locate a second decision row in the same session with a different `agent_role` for the same prompt class; confirm verdicts differ in the predicted direction (reviewer SUGGEST/BLOCK on CLI exec, developer GUIDE/INTERVENE on hot-zone target).

## PASS criteria

- `decision_id` present, verdict in {ALLOW, SUGGEST, INTERVENE, BLOCK, AMBIGUOUS}, band populated.
- ≥ 1 bias row attached.
- **§4 row PASS:** alignment + cadence signals present in metadata.
- Role-binding divergence observed OR `partial-evidence-single-role` (coordinator escalates to C10 for negative-test injection).

## Outputs to coordinator

- `decision_id` for C5 dashboard probe.
- INTENT §4 row read (PASS/under-served).
- Role-binding row read (confirmed/partial/absent).

## Failure modes

- `no-decision-for-envelope` — governance dropped the envelope; HARD FAIL.
- `intent-undelivered` — no alignment+cadence in metadata; §4 row FAIL (POC may still SHIP with a §3-only PASS — coordinator decides).
- `role-divergence-not-observed` — escalate to C10 for negative-test injection.

## Refs

- `src/stream_manager/governance.py` (FROZEN).
- `src/stream_manager/agent_registry.py`.
- INTENT.md §"Plan alignment + cadence", §"Sub-agent governance principles", §"Hot zones".
