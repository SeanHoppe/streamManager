# Task — Cassette CI guard (#132): enforce same-PR coverage for new bus envelope kinds

> Standalone hardening task. NOT a phase prompt — folds into v2.2 P0
> hygiene PR or runs as standalone PR after v2.2 P0 lands. Bootstrap
> baseline NOW available because v2.1 P1–P3 shipped `audit.probe` /
> `audit.probe_ack` / `audit.canary_emit` / `audit.canary_observed` /
> `audit.probe_failure` / `audit.hallucination_detected` envelope
> kinds.

## Why

Memory `feedback_cassette_must_cover_new_envelopes.md`: v1.3 nearly
tagged without LM cassette coverage. Probability of recurrence → 1
over enough cycles. Rule = convention-only today. Make it a hard CI
guard.

## Option B (recommended per issue #132) — source-of-truth allowlist

Add `src/stream_manager/envelope_kinds.py` (new module, ~30 LOC):

```python
# Canonical allowlist of envelope kinds the bus may publish.
# Adding a new kind requires updating this list AND cassette + soak
# driver coverage in the same PR (enforced by tests/test_envelope_coverage.py).
ENVELOPE_KINDS = frozenset({
    "governance_decision",
    "desktop_command",
    "audit.probe",
    "audit.probe_ack",
    "audit.canary_emit",
    "audit.canary_observed",
    "audit.probe_failure",
    "audit.hallucination_detected",
    # ... existing kinds — enumerate from grep of `bus.publish` / `write_envelope` callsites
})
```

Cross-reference existing `KIND_ALLOWLIST` at
`src/stream_manager/desktop_commands.py:39-48` — that allowlist covers
`desktop_command` SUB-kinds; this is the outer bus envelope kind.
Decide whether to unify or keep parallel.

## Sentinel test (`tests/test_envelope_coverage.py`)

For each kind in `ENVELOPE_KINDS`, assert:

1. Recorded by `tools/cassette_record.py` (grep cassette source for the
   kind string OR run a sample record + parse output to confirm).
2. Replayable via `tools/soak_driver.py` cassette mode (assert the
   driver registers a handler for the kind OR passes it through pubsub
   without raising).

## Backfill audit

Before merge, run:

```bash
grep -rn "bus.publish\|write_envelope" src/ dashboard/ tools/ | grep -oE 'kind=[a-z._]+' | sort -u
```

Reconcile against `ENVELOPE_KINDS`. Any kind grepped but not in
allowlist → either add (if intended) or fix the callsite. Any kind in
allowlist but not grepped → suspicious; investigate before merge.

## Failure-path test

Deliberately add `"audit.fake_kind"` to `ENVELOPE_KINDS` without
cassette/soak coverage. Run pytest. Test MUST fail with a clear
"new envelope kind missing cassette coverage" error.

## DOD

- [ ] `src/stream_manager/envelope_kinds.py` added with full allowlist.
- [ ] Backfill audit clean (existing kinds reconciled or marked exempt
      with reason).
- [ ] `tests/test_envelope_coverage.py` covers every kind.
- [ ] Failure-path test demonstrated (locally) before removing the
      synthetic broken row.
- [ ] `feedback_cassette_must_cover_new_envelopes.md` updated:
      "convention" → "enforced rule (test:
      `tests/test_envelope_coverage.py`)".
- [ ] Issue #132 closed on merge.

## ADR-18 posture

Additive: new module + new test. No FROZEN seam touched. LOC budget
~50 src + ~80 tests = ~130 LOC. Counts against feature-cycle budget if
folded into v2.2; counts against consolidation budget if v2.2 is
consolidation (would need offset).

## Cross-references

- Issue #132: `docs/jobs/issue-132.md`.
- Memory `feedback_cassette_must_cover_new_envelopes.md`.
- Existing allowlist: `src/stream_manager/desktop_commands.py:39-48`.
- v1.3 incident: memory `project_v13_corrective.md`.
