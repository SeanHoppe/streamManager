You are implementing **Phase P2 — PPP Layer 2 canary echo** for
the streamManager v2.1 cycle (PPP audit harness). P1 (PR #138) +
P1a (PR #141) shipped Layer 1 disambiguation; the signed
`provenance_assertions` row + sig_v=2 enrichment (brain_id +
prompt_hash) is the input for Layer 2.

## Branch + base

- Base: `main` after v2.1 P1 + P1a merged (HEAD `863175e` or
  later).
- PR target: `main`.
- Branch: `feat/v2.1-p2-ppp-canary-echo`.

## Reference docs (load before coding)

- `docs/v2.1-p2-scope.md` — **load-bearing** scope + LOC tracker +
  milestone breakdown + R-register. Authority for all decisions
  noted as "inherited" below.
- `docs/v2.1-task-plan.md` — cycle frame.
- `docs/v2.1-p1-scope.md` — P1 reference (envelope shapes, sig
  payload schema, threat model lock).
- `docs/v1.7-backlog.md` §"🟢 PPP audit harness" — Layer 2
  original scope.
- `REQUIREMENTS.md` §4.13 FR-PPP-1..7 — existing PPP requirements.
- Memory: `feedback_no_self_monitor.md`,
  `feedback_cassette_must_cover_new_envelopes.md`,
  `feedback_cross_pr_seam_review.md`,
  `feedback_subagent_stale_mental_model.md`.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface freeze in force. P2 touches ONLY:

- `src/stream_manager/message_bus.py` — 3 new envelope dataclasses
  (`AuditCanaryEmitEnvelope`, `AuditCanaryObservedEnvelope`,
  `AuditProbeFailureEnvelope`) + idempotent ALTER on
  `provenance_assertions` adding `canary_nonce TEXT` +
  `canary_confirmed_at REAL`. Existing tables + writers
  UNCHANGED.
- `src/stream_manager/governance.py` — `emit_audit_canary` +
  `emit_audit_probe_failure` peers to existing
  `emit_audit_probe`.
- `src/stream_manager/jsonl_tail.py` — per-process canary
  registry + observer + 1s sweep loop. Existing ingest path
  UNCHANGED (new hook is additive).
- `dashboard/server.py` — `POST /api/sm-canary/emit` +
  auto-emit hook on `/api/sm-probe/ack` success path. SSE
  bridge extends for 3 new envelope types via existing per-conn
  subscriber.
- `dashboard/static/index.html` — `.hitl-item-canary` row
  variant + nonce display + countdown bar.
- `tools/cassette_record.py` — `_record_canary_envelopes` under
  existing `--skip-ppp-pump` flag.
- `tests/test_audit_canary_envelope.py` (new)
- `tests/test_audit_canary_observe.py` (new)
- `tests/test_audit_canary_cassette.py` (new)
- `REQUIREMENTS.md` — append FR-PPP-8..11.

NO edits to `cli_pool.py`, `cli_governance.py`, `model_router.py`,
`_last_phase_timings_ms` keys, `_L2_L3_TRIGGER` corpus,
`_ALLOW_PHASE_ORDER`, or any FROZEN bus envelope schema (Layer 1
envelopes UNCHANGED — sig_v=2 enrichment from P1a is preserved
verbatim). NO deletions; NO renames.

Pre-flight grep:

```
grep -nE 'audit\.canary|audit_canary|audit\.probe_failure|canary_nonce|canary_confirmed_at' src/ tests/ tools/ dashboard/
```

Before P2 edits: zero hits except docs (this prompt + scope doc).
After P2 edits: hits in the files listed above and nowhere else.

## Task brief

Per `docs/v1.7-backlog.md` §"🟢 PPP audit harness — Provenance
Probe Protocol" Layer 2, implement the canary-echo binding proof:

1. **Nonce emit** — after operator signs a Layer-1 assertion, SM
   emits `audit.canary_emit` carrying `{probe_id, jsonl_path,
   nonce, issued_at, timeout_s, hmac_sig}`. Nonce is 16-byte hex
   (`secrets.token_hex(8)`). Default `timeout_s=10`.
2. **Operator surfaces** — dashboard renders the nonce in a
   `.hitl-item-canary` row with a countdown bar; operator types
   the nonce into their active Claude CLI session.
3. **Observer** — `JsonlTailWorker` scans new user-text turns;
   on nonce match with the same `jsonl_path` as the registered
   canary entry, SM emits `audit.canary_observed`, calls
   `bus.mark_canary_confirmed(probe_id, nonce, confirmed_at)`, and
   clears the registry entry.
4. **Timeout fallback** — 1s sweep loop scans the registry for
   entries older than `timeout_s`; on timeout SM emits
   `audit.probe_failure` (reason=`canary_timeout`) and re-fires
   Layer 1 disambiguation HITL via `emit_audit_probe_failure`.
5. **Self-monitor guard** — observer MUST NOT scan SM's own
   JSONL. Reuse the `_is_sm_originated` ingest filter already in
   place per `feedback_no_self_monitor.md`.
6. **Cassette coverage** — `tools/cassette_record.py` records all
   3 new envelope types same-cycle per
   `feedback_cassette_must_cover_new_envelopes.md`.

### Threat model continuity

Per FR-PPP-2 lock (2026-05-10), all canary sigs are
**endpoint-integrity**, not operator-attestation. Server signs at
emit / observe / failure time using the `desktop_command` secret
of record. Browser does NOT hold the secret. Sig defends against
direct envelope tampering by processes that lack the secret. The
canary signature schema is independent of the ack sig_v field;
canary sigs are sig_v=1 (canary fields are intrinsic to the
envelope, no schema versioning needed yet).

### Deliverables — see milestone breakdown

See `docs/v2.1-p2-scope.md` §4 "Deep-coding milestones" for the
M1 → M6 breakdown. Each milestone is a check-in point with a
diff-stat report.

## DOD

- [ ] Envelopes `audit.canary_emit` / `audit.canary_observed` /
      `audit.probe_failure` defined + tested
- [ ] `provenance_assertions` ALTER adds `canary_nonce TEXT` +
      `canary_confirmed_at REAL` idempotently
- [ ] `emit_audit_canary` + `emit_audit_probe_failure` in
      `governance.py` (peers to `emit_audit_probe`)
- [ ] `JsonlTailWorker` nonce observer + 1s sweep loop
- [ ] `POST /api/sm-canary/emit` + auto-emit hook on ack success
- [ ] `.hitl-item-canary` row variant renders + auto-clears on
      observed / flips to failure on probe_failure
- [ ] Cassette coverage extended same-cycle (per
      `feedback_cassette_must_cover_new_envelopes.md`)
- [ ] Self-monitor guard: observer skips SM's own JSONL via
      `_is_sm_originated`
- [ ] All 3 test files added; full suite green via
      `pytest -m "not slow and not alignment_eval"`
- [ ] LOC budget ≤ 700 net add (split to P2a per ADR-18 Rule 4
      if exceeded; same pattern as P1 → P1a)
- [ ] FROZEN-seam diff guard: zero non-additive hunks
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `feat(ppp):`
- [ ] `REQUIREMENTS.md` FR-PPP-8..11 appended
- [ ] Sub-cycle close-out diff PR head vs base on FROZEN seam
      files (`message_bus.py`, `governance.py`, `jsonl_tail.py`,
      `desktop_commands.py`) per
      `feedback_subagent_stale_mental_model.md`
- [ ] Cross-PR seam review (writer↔reader pairs) per
      `feedback_cross_pr_seam_review.md` and the seam table in
      `docs/v2.1-p2-scope.md` §6

## After this phase

P2 close-out mints `docs/prompts/v2.1-orchestration/phase-3-ppp-negative-control.md`
(Layer 3 — negative-control synthetic stream + self-monitor hard
guard). P3 graduates the P1a candidate-list filter from
defense-in-depth to hard guard and adds the synthetic-stream
hallucination detector.
