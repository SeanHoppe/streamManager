You are implementing **Phase P3 — PPP Layer 3 negative-control +
self-monitor hard guard** for the streamManager v2.1 cycle (PPP
audit harness). P1 (PR #138) shipped Layer 1 stream
disambiguation; P1a (PR #141) drained Layer 1 follow-ups + added
the P1a defense-in-depth `sm_brain_id` filter at
`session_watcher.build_audit_probe_candidates`; P2 (PR #143)
shipped Layer 2 canary echo (3 envelope types + observer + 1s
sweep + dashboard `.hitl-item-canary` row).

## Branch + base

- Base: `main` after v2.1 P2 merged (HEAD `4b755f6` or later).
- PR target: `main`.
- Branch: `feat/v2.1-p3-ppp-negative-control`.

## Reference docs (load before coding)

- `docs/v2.1-p3-scope.md` — **load-bearing** scope + LOC tracker +
  milestone breakdown + R-register. Authority for all decisions
  noted as "inherited" below. **Mint this scope doc as M0 before
  any coding.**
- `docs/v2.1-task-plan.md` — cycle frame; §"PHASE P3" stub.
- `docs/v2.1-p1-scope.md` + `docs/v2.1-p2-scope.md` — predecessor
  layer references (envelope shapes, sig payload schema, threat
  model lock, FROZEN-seam discipline).
- `docs/v1.7-backlog.md` §"🟢 PPP audit harness" Layer 3 — original
  scope: synthetic JSONL never written + dashboard hallucination
  detector + self-monitor brain_id hard guard.
- `REQUIREMENTS.md` §4.13 FR-PPP-1..11 — existing PPP requirements;
  P3 appends FR-PPP-12..14.
- Memory: `feedback_no_self_monitor.md` (load-bearing — the hard
  guard exists because of this rule),
  `feedback_cassette_must_cover_new_envelopes.md`,
  `feedback_cross_pr_seam_review.md`,
  `feedback_subagent_stale_mental_model.md`,
  `feedback_subagent_escape_hatches.md`,
  `feedback_parallel_undisclosed_deviations.md`.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface freeze in force. P3 touches ONLY:

- `src/stream_manager/message_bus.py` — 1 new envelope dataclass
  (`AuditHallucinationDetectedEnvelope`) + 1 new WAL table
  (`provenance_decoys`: probe_id, jsonl_path, registered_at,
  triggered_at, hmac_sig). Existing tables + writers + Layer-1/2
  envelopes UNCHANGED.
- `src/stream_manager/session_watcher.py` — graduate `sm_brain_id`
  from optional kwarg (P1a defense-in-depth) to MANDATORY (P3 hard
  guard). Signature: drop the `None` default. All call sites must
  resolve `SM_OWN_SESSION_ID` and pass it; missing env var ⇒ raise
  `RuntimeError("SM_OWN_SESSION_ID required for audit-probe
  candidate build")`. Enumerate every call site at M0.
- `src/stream_manager/governance.py` — `register_decoy_stream` +
  `emit_audit_hallucination_detected` peers to
  `emit_audit_canary` / `emit_audit_probe_failure`. Decoy
  registration writes a `provenance_decoys` row; hallucination
  envelope fires when the parser/tail/observer reports activity on
  a path that matches a registered decoy.
- `src/stream_manager/jsonl_tail.py` — decoy-path detection hook.
  Tail worker MUST NOT subscribe to a decoy path (parser
  hallucination would create the file as a side-effect of
  watching); the hook fires when any code path reports a parsed
  record whose `jsonl_path` is a registered decoy. Reuse the
  existing `_is_sm_originated` filter pattern.
- `dashboard/server.py` — `POST /api/sm-decoy/register` (operator-
  triggered or auto-fired at SM boot). SSE bridge extends for
  `audit.hallucination_detected` envelope via existing per-conn
  subscriber.
- `dashboard/static/index.html` — `.hitl-item-hallucination` row
  variant (RED — this is a parser-correctness alarm, not an
  operator-attestation prompt). Reuses the `.hitl-item-canary`
  CSS scaffold.
- `tools/cassette_record.py` — `_record_decoy_envelopes` extends
  the existing `_record_ppp_envelopes` helper under the existing
  `--skip-ppp-pump` flag (no new flag).
- `tests/test_audit_decoy_register.py` (new) — register + WAL row
  shape + hmac sig.
- `tests/test_audit_hallucination_envelope.py` (new) — envelope
  round-trip + sig binds `jsonl_path` + `probe_id`.
- `tests/test_audit_hallucination_detect.py` (new) — synthetic
  parser report on a registered decoy path triggers
  `audit.hallucination_detected` envelope + WAL row update;
  unregistered path is a no-op.
- `tests/test_audit_self_monitor_hardguard.py` (new) — P1a
  `sm_brain_id` optional-kwarg ⇒ P3 mandatory: missing
  `SM_OWN_SESSION_ID` raises; passing matching `sessionId` drops
  the row; existing P1a defense-in-depth tests still pass.
- `tests/test_audit_decoy_cassette.py` (new) — cassette covers
  `audit.hallucination_detected` envelope + decoy registration row.
- `REQUIREMENTS.md` — append FR-PPP-12..14.

NO edits to `cli_pool.py`, `cli_governance.py`, `model_router.py`,
`_last_phase_timings_ms` keys, `_L2_L3_TRIGGER` corpus,
`_ALLOW_PHASE_ORDER`, or any FROZEN bus envelope schema (Layer 1
and Layer 2 envelopes UNCHANGED — `audit.probe`,
`audit.probe_ack`, `audit.canary_emit`, `audit.canary_observed`,
`audit.probe_failure` schemas preserved verbatim). NO deletions;
NO renames. The P1a `brain_id_filter` kwarg on
`build_audit_probe_candidates` STAYS (used by self-monitor test
fixtures); P3 only changes `sm_brain_id` from optional to
mandatory.

Pre-flight grep:

```
grep -nE 'audit\.hallucination|audit_hallucination|provenance_decoys|register_decoy|decoy_stream|AuditHallucination' src/ tests/ tools/ dashboard/
```

Before P3 edits: zero hits except docs (this prompt + scope doc).
After P3 edits: hits in the files listed above and nowhere else.

Self-monitor surface enumeration (M0 deliverable — confirm at
least these five sites before any edits):

```
grep -nE 'SM_OWN_SESSION_ID|_is_sm_originated|sm_brain_id|_is_self_session|is_self_monitor_path' src/
```

Expected sites (P1 + P1a + P2 surface):
1. `desktop_commands.py:127-134` — sign-time guard (raises on
   self-match)
2. `governance.py:1547+` — `_sm_own_session_id` accessor +
   evaluate-time guard
3. `jsonl_tail.py:345+` — `_is_sm_originated` ingest filter
4. `session_watcher.py:411` — P1a `sm_brain_id` drop (P3 promotes
   to mandatory)
5. `learn_mode.py:208+` — `_filter_self_monitor` for LM ingest

M0 scope doc enumerates these + confirms P3 only mutates site #4
(promotion to mandatory) and adds the negative-control surface
peer to site #3 (decoy-path detection in `jsonl_tail.py`).

## Task brief

Per `docs/v1.7-backlog.md` §"🟢 PPP audit harness" Layer 3,
implement the negative-control + self-monitor hard guard:

1. **Negative-control decoy registration** — operator (or SM at
   boot) registers a synthetic JSONL path that is never written.
   Path shape: `~/.claude/projects/<decoy-slug>/<decoy-uuid>.jsonl`
   where `<decoy-uuid>` is a fresh `secrets.token_hex(16)` and
   `<decoy-slug>` is a sentinel literal `sm-decoy-control`. Row
   lands in `provenance_decoys` WAL table; HMAC sig binds
   `{probe_id, jsonl_path, registered_at}` (sig_v=1, endpoint-
   integrity per FR-PPP-2).
2. **Hallucination detector** — when ANY code path inside
   `jsonl_tail` / `session_watcher` / `governance` reports a
   parsed record or candidate row whose `jsonl_path` matches a
   registered decoy, SM emits `audit.hallucination_detected`
   envelope and updates the `provenance_decoys.triggered_at`
   column. The envelope is a RED dashboard alarm (parser is
   producing fictional records). Single-emit per
   `(probe_id, jsonl_path)` pair — second match is a no-op
   (pop-then-emit pattern from P2 R7 mitigation).
3. **Self-monitor hard guard** — promote P1a
   `session_watcher.build_audit_probe_candidates(sm_brain_id=...)`
   from optional kwarg (defense-in-depth) to mandatory. Calling
   without a resolved `SM_OWN_SESSION_ID` raises
   `RuntimeError`. Existing P1a callers gain a single line to
   resolve the env var at call time; no behavior change for
   correctly-configured deployments. Failure-mode flips from
   silent ("filter not applied") to loud (immediate exception at
   the call site) per `feedback_no_self_monitor.md`.
4. **Dashboard surface** — `.hitl-item-hallucination` row variant
   (RED border + alarm icon) renders on `audit.hallucination_detected`
   SSE. Does NOT auto-clear — operator must dismiss explicitly
   (this is a correctness alarm, not a request for input).
5. **Cassette coverage** — `tools/cassette_record.py` extends the
   PPP envelope helper to record `audit.hallucination_detected`
   same-cycle per `feedback_cassette_must_cover_new_envelopes.md`.
6. **No self-monitor regression** — P2 observer's existing
   `_is_sm_originated` filter MUST still fire before any decoy
   match (defense in depth: SM's own JSONL would also be a
   spurious-activity source).

### Threat model continuity

Per FR-PPP-2 lock (2026-05-10), all hallucination-detector sigs
are **endpoint-integrity**, not operator-attestation. Server signs
at registration time + hallucination-detection time using the
`desktop_command` secret of record. Browser does NOT hold the
secret. The decoy path itself is unsigned (anyone reading the WAL
sees the synthetic path) — confidentiality is not a requirement;
integrity of the registration row + detection envelope is.

### Deliverables — see milestone breakdown

M0 — mint `docs/v2.1-p3-scope.md` with self-monitor surface
enumeration, LOC tracker, milestone breakdown, R-register. NO
code edits in M0.

M1 — envelope + WAL table (`message_bus.py`, ~50 LOC).
M2 — governance peers (`governance.py`, ~50 LOC).
M3 — self-monitor hard-guard graduation (`session_watcher.py` +
all call-site fix-ups, ~30 LOC including each call-site one-liner
to resolve `SM_OWN_SESSION_ID`).
M4 — decoy-path detection hook (`jsonl_tail.py`, ~40 LOC).
M5 — dashboard surface (`server.py` + `index.html`, ~80 LOC).
M6 — cassette + 4 test files + REQUIREMENTS append + verify
(~140 LOC).

**Total LOC estimate: ~390 net add.** Well under ADR-18 Rule 4
700-cap soft target. If P3 draft exceeds 700, split P3a per Rule
4 — but P3 is intentionally smaller than P1/P2 (the surface is
already in place; P3 graduates + adds the decoy seam).

## DOD

- [ ] `docs/v2.1-p3-scope.md` minted at M0 with self-monitor
      surface enumeration + LOC tracker + milestone breakdown +
      R-register
- [ ] Envelope `audit.hallucination_detected` defined + tested
- [ ] `provenance_decoys` WAL table migrates idempotently
- [ ] `register_decoy_stream` + `emit_audit_hallucination_detected`
      in `governance.py` (peers to `emit_audit_canary`)
- [ ] `session_watcher.build_audit_probe_candidates` `sm_brain_id`
      is MANDATORY (no `None` default); missing env var ⇒ raises
- [ ] All P1 / P1a / P2 call sites of `build_audit_probe_candidates`
      pass a resolved `SM_OWN_SESSION_ID` (no test fixtures use
      `None`; all real callers use the env-var resolver)
- [ ] `jsonl_tail` decoy-path detection: any parsed record on a
      registered decoy path ⇒ `audit.hallucination_detected`
- [ ] `POST /api/sm-decoy/register` endpoint registers + returns
      `{probe_id, jsonl_path, hmac_sig}`
- [ ] `.hitl-item-hallucination` row variant renders RED;
      operator-dismiss only (no auto-clear)
- [ ] Cassette coverage extended same-cycle (per
      `feedback_cassette_must_cover_new_envelopes.md`)
- [ ] P2 `_is_sm_originated` filter fires before decoy match
      (defense in depth preserved)
- [ ] All 4 test files added; full suite green via
      `pytest -m "not slow and not alignment_eval"`
- [ ] LOC budget ≤ 700 net add (target ~390; split to P3a per
      ADR-18 Rule 4 if exceeded — same pattern as P1 → P1a)
- [ ] FROZEN-seam diff guard: zero non-additive hunks on
      `message_bus.py`, `governance.py`, `jsonl_tail.py`,
      `desktop_commands.py`. `session_watcher.py` has ONE
      non-additive hunk (kwarg-default removal) — disclosed
      up-front in PR body, NOT silent
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `feat(ppp):`
- [ ] `REQUIREMENTS.md` FR-PPP-12..14 appended
- [ ] Sub-cycle close-out diff PR head vs base on FROZEN seam
      files per `feedback_subagent_stale_mental_model.md`
- [ ] Cross-PR seam review (writer↔reader pairs) per
      `feedback_cross_pr_seam_review.md` and the seam table in
      `docs/v2.1-p3-scope.md` §6
- [ ] P2 observer dormant-wiring follow-up: P3 is NOT the place to
      wire `JsonlTailWorker.start()` into dashboard app startup
      (separate task). P3 disclosure: if M4 decoy hook can be
      exercised end-to-end without a started worker, ship; if not,
      M4 tests use direct hook calls (same pattern as P2
      `_process_line` tests) and the dormant-observer note from
      PR #143 carries forward

## After this phase

P3 close-out mints `docs/prompts/v2.1-orchestration/phase-4-ship-gate-finalize.md`
(v2.1 ship-gate). P4 runs Tier 3 soak with PPP auto-probe enabled
(default-on flip from P1's opt-in), alignment-eval `--ci-gate`,
ADR-5 v2.1 baseline append, CHANGELOG v2.1.0, tag v2.1.0, mint
`project_v21_cycle_close.md`, close the 🟢 PPP audit harness seed
in `docs/v1.7-backlog.md` via tail-of-entry graduation note (no
emoji edit per frozen-emoji rule), and roll any new findings into
`docs/v2.2-backlog.md`.

P4 ship-gate inherits the dormant-observer follow-up from PR #143
+ the (likely) dormant decoy-hook follow-up from this PR: ship-
gate verification MUST either wire `JsonlTailWorker.start()` into
dashboard app startup OR record the dormant state in
`project_v21_cycle_close.md` with a v2.2 backlog seed for the
wiring task.
