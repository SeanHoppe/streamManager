You are implementing **Phase P1 — PPP Layer 1 stream
disambiguation** for the streamManager v2.1 cycle (PPP audit
harness). Sync-comms v1.0 (Tasks D/E/F/K) shipped in v1.0–v1.2 and
unblocks PPP. v2.1 cycle is a feature cycle; ADR-18 surface freeze
in force; PPP surface is purely additive.

## Branch + base

- Base: `main` after v2.1 P0 merged.
- PR target: `main`.
- Branch: `feat/v2.1-p1-ppp-stream-disambiguation` (or operator's
  choice).

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P1 must touch ONLY:

- `src/stream_manager/desktop_commands.py` — extend allowlist with
  `"audit_probe"` kind. Existing kinds + schema UNCHANGED.
- `src/stream_manager/desktop_command_consumer.py` — add
  `audit_probe` handler peer to existing kind handlers.
- `src/stream_manager/hitl.py` — add `AUDIT_PROBE = "audit_probe"`
  to the `TriggerReason` enum (peer to `CROSS_SESSION_FLAG`).
- `src/stream_manager/governance.py` — add `/sm-probe` invocation
  point that emits a HITL queue entry with
  `trigger_reason="audit_probe"` (peer to existing
  `cross_session_flag` site at line 1231).
- `src/stream_manager/message_bus.py` — add `provenance_assertions`
  WAL table migration (peer to `desktop_commands` table).
  Existing tables + writers UNCHANGED.
- `src/stream_manager/session_watcher.py` — read-only consumer for
  candidate-list snapshot. No signature change.
- `dashboard/server.py` — add `/sm-probe` HTTP endpoint and SSE
  stream entry for the new envelope pair.
- `dashboard/static/index.html` — add audit-probe row variant in
  the existing HITL panel section. Pattern matches the existing
  `cross_session_promotion` row.
- `tools/cassette_record.py` — extend with `audit.probe` /
  `audit.probe_ack` envelope coverage.
- `tools/soak_driver.py` — accept opt-in `--ppp-auto-probe` flag
  (default off in P1; default-on slips to P4). Existing flags
  UNCHANGED.
- `tests/test_audit_probe_envelope.py` (new)
- `tests/test_audit_probe_hitl.py` (new)
- `tests/test_audit_probe_cassette.py` (new)
- `tests/test_audit_probe_self_monitor.py` (new)
- `REQUIREMENTS.md` — append FR-PPP-1..N section.

NO edits to `cli_pool.py`, `cli_governance.py`, `model_router.py`,
`_last_phase_timings_ms` keys, `_L2_L3_TRIGGER` corpus,
`_ALLOW_PHASE_ORDER`, or any FROZEN bus envelope schema. NO
deletions; NO renames.

Pre-flight grep:

```
grep -nE 'audit_probe|audit\.probe|provenance_assertion' src/ tests/ tools/ dashboard/
```

Before P1 edits: zero hits except docs / task plan / phase-0
prompt. After P1 edits: hits in the eleven files listed above and
nowhere else.

## Task brief

Per `docs/v1.7-backlog.md` §"🟢 PPP audit harness — Provenance
Probe Protocol" Layer 1, implement runtime stream-binding
disambiguation:

1. **Envelope pair** `audit.probe` / `audit.probe_ack` — new bus
   message types. Probe payload carries top-K candidate streams
   SM is currently watching; ack carries operator's selection (or
   "none") + signed provenance assertion.
2. **`/sm-probe` endpoint** — on-demand HITL question. Returns
   cached assertion if not expired (TTL ~30 min); else fires fresh
   probe via the existing SSE transport from ADR-14.
3. **HITL panel section** — render audit-probe rows with
   candidate-list radio buttons + "none" option; pattern matches
   existing `cross_session_promotion` row variant in HITL panel.
4. **WAL `provenance_assertions` table** — id, session_id,
   jsonl_path, brain_id, prompt_hash, signed_at, expires_at,
   hmac_sig. Resolution of an audit_probe HITL row writes one row
   here. Future P2 (canary echo) reads from it.
5. **Cassette coverage** — extend `tools/cassette_record.py` with
   the new envelope pair same-cycle per
   `feedback_cassette_must_cover_new_envelopes.md`.
6. **Self-monitor candidate-list filter** (defense-in-depth
   preview; full guard lands in P3) — exclude any JSONL whose
   `brain_id` matches SM's own brain_id from the candidate list.

### Deliverables

1. **Envelope pair `audit.probe` / `audit.probe_ack`**:

   - `audit.probe` payload (TypedDict / dataclass at the existing
     bus message-type definition site):
     ```python
     {
         "candidate_streams": [
             {
                 "slug": str,
                 "jsonl_path": str,
                 "brain_id": str,
                 "last_event_ts": float,  # epoch seconds
                 "prompt_hash": str,
             },
             # top-K, K = 5 default; configurable via session config
         ],
         "ttl_seconds": int,  # default 1800 (30 min)
         "hmac_sig": str,
     }
     ```
   - `audit.probe_ack` payload:
     ```python
     {
         "selected_jsonl_path": str | None,  # None == "operator picked 'none'"
         "signed_at": float,  # epoch seconds
         "expires_at": float,
         "hmac_sig": str,
     }
     ```
   - HMAC sig algorithm = SHA-256 over `(slug || jsonl_path ||
     brain_id || last_event_ts || prompt_hash || ttl_seconds)`,
     keyed by the existing shared secret resolved per OQ1
     (env `SM_DESKTOP_SECRET` first → `.bridge/secret`
     fallback). Reuse the secret-resolution helper from
     `desktop_commands.py`; do NOT re-implement.

2. **WAL `provenance_assertions` table** — additive migration in
   `message_bus.py`:

   ```sql
   CREATE TABLE IF NOT EXISTS provenance_assertions (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       session_id TEXT NOT NULL,
       jsonl_path TEXT,  -- NULL when operator selected "none"
       brain_id TEXT,
       prompt_hash TEXT,
       signed_at REAL NOT NULL,
       expires_at REAL NOT NULL,
       hmac_sig TEXT NOT NULL
   );
   CREATE INDEX IF NOT EXISTS idx_provenance_session_active
       ON provenance_assertions (session_id, expires_at DESC);
   ```

   Migration runs on `MessageBus.__init__` next-startup; idempotent
   `IF NOT EXISTS`. No backfill; assertions accrue as probes fire.

3. **`audit_probe` HITL trigger reason** — extend
   `hitl.py:TriggerReason` enum:

   ```python
   class TriggerReason(StrEnum):
       LOW_CONFIDENCE = "low_confidence"
       NEW_PATTERN = "new_pattern"
       DESKTOP_PAUSE = "desktop_pause"
       CROSS_SESSION_FLAG = "cross_session_flag"
       AUDIT_PROBE = "audit_probe"  # NEW
   ```

4. **`/sm-probe` endpoint** in `dashboard/server.py`:

   - `GET /api/sm-probe?session_id=X&force=0|1` — returns current
     non-expired assertion, OR (if expired or `force=1`) fires new
     `audit.probe` and returns 202 with the in-flight HITL row id.
   - `POST /api/sm-probe/ack` — body =
     `{hitl_row_id, selected_jsonl_path | null}`; validates HMAC
     sig, writes `provenance_assertions` row, resolves HITL row.
   - HMAC sig validation reuses existing helper from
     `desktop_commands.py`; do NOT duplicate logic.
   - SSE stream entry for `audit.probe` envelope rides the existing
     ADR-14 transport — no new transport.

5. **Dashboard HITL panel section** — extend
   `dashboard/static/index.html`:

   - New row variant for `decision_type="audit_probe"`:
     candidate-list radio buttons (top-5 streams), "none"
     fallback, "approve selected" button.
   - Render uses existing `.hitl-panel` / `.hitl-item` /
     `.hitl-bar` classes (no new CSS unless candidate-list
     rendering needs minimal additions).
   - On submit → `POST /api/sm-probe/ack` → assertion written →
     HITL row resolved.

6. **Auto-probe cadence** in `tools/soak_driver.py`:

   - New flag `--ppp-auto-probe` (default OFF in P1).
   - When set, soak driver fires `/api/sm-probe?force=1` every
     1800 s of soak wall-clock.
   - Default flip to ON happens in P4 ship-gate (NOT P1).

7. **Self-monitor candidate-list filter** (defense-in-depth):

   - Candidate-list builder filters out any JSONL whose `brain_id`
     equals SM's own brain_id (resolved via the existing
     no-self-monitor helper used by `session_watcher.py`).
   - Test asserts this filter; full hard guard lands in P3 over
     the entire candidate-discovery surface.

8. **Cassette coverage** in `tools/cassette_record.py`:

   - Extend the envelope-type allowlist with `audit.probe` and
     `audit.probe_ack`. Capture both envelopes in soak replay.
   - `tools/soak_driver.py --cli-replay` round-trips both
     envelopes byte-identical to live capture.

9. **Tests**:

   - `tests/test_audit_probe_envelope.py`:
     - `test_audit_probe_payload_round_trip` — encode/decode is
       lossless.
     - `test_audit_probe_hmac_sig_round_trip` — sig validates;
       wrong key fails.
     - `test_audit_probe_ttl_expiry` — assertion past
       `expires_at` is rejected.
     - `test_audit_probe_ack_none_selection` —
       `selected_jsonl_path=None` writes a NULL row + valid sig.

   - `tests/test_audit_probe_hitl.py`:
     - `test_audit_probe_emits_hitl_row` —
       `/api/sm-probe?force=1` writes a `hitl_pending` row with
       `trigger_reason="audit_probe"`.
     - `test_audit_probe_ack_resolves_hitl_row` — ack POST resolves
       the HITL row + writes `provenance_assertions` row.
     - `test_cached_assertion_skips_probe` —
       `/api/sm-probe?force=0` with non-expired assertion returns
       cached row, fires no probe.

   - `tests/test_audit_probe_cassette.py`:
     - `test_cassette_captures_audit_probe_pair` — live capture +
       replay round-trips both envelopes.

   - `tests/test_audit_probe_self_monitor.py`:
     - `test_candidate_list_excludes_sm_own_brain_id` — when SM's
       own JSONL is in the watch set, `/api/sm-probe` candidate
       list does NOT include it.

10. **REQUIREMENTS.md** — append §"FR-PPP — Provenance Probe
    Protocol" with:

    - FR-PPP-1: SM MAY emit `audit.probe` envelopes asking the
      operator to identify which currently-watched JSONL stream
      is the one being driven.
    - FR-PPP-2: Operator response (`audit.probe_ack`) MUST be
      HMAC-signed with the shared sync-comms secret.
    - FR-PPP-3: A valid acknowledgement creates a
      `provenance_assertions` WAL row with TTL ≥ 30 min.
    - FR-PPP-4: Cached non-expired assertions short-circuit
      subsequent `/sm-probe` requests (no probe re-fired until
      expiry or `force=1`).
    - FR-PPP-5: Candidate-list builder MUST filter out SM's own
      brain_id from the choices presented to the operator.
    - FR-PPP-6: PPP envelope schemas MUST be covered by the soak
      cassette in the same release that introduces them.

### LOC budget

P1 net add ≤ 700 lines (envelope pair + WAL table + HITL trigger +
HTTP/SSE endpoints + dashboard panel section + cassette coverage +
tests + REQUIREMENTS). If draft exceeds, split to a P1a sub-phase
(requires v2.1 cycle-frame amendment per ADR-18 Rule 4).

### Cross-PR seam review (REQUIRED before merge)

Per `feedback_cross_pr_seam_review.md`: at sub-cycle close-out,
audit writer↔reader pairs against the design doc component table:

| Writer | Reader | Verify |
|---|---|---|
| `/sm-probe` endpoint emits `audit.probe` | `desktop_command_consumer` handler | payload schema matches |
| `/api/sm-probe/ack` writes WAL row | future P2 canary observer reads | column set matches the table created here |
| Cassette captures both envelopes | Soak driver replay reads cassette | byte-identical round-trip |
| Dashboard renders HITL row | `governance.py:1231`-peer emits HITL row | `decision_type` + `trigger_reason` consistent |
| Candidate-list builder filters SM's own brain_id | Self-monitor test asserts the filter | filter applied at the right call site |

### Sub-cycle close-out diff guard

Per `feedback_subagent_stale_mental_model.md`: BEFORE final merge,
diff PR head vs base (`origin/main`) on the FROZEN seam files:

```
git --no-pager diff origin/main..HEAD -- \
  src/stream_manager/desktop_commands.py \
  src/stream_manager/hitl.py \
  src/stream_manager/governance.py \
  src/stream_manager/message_bus.py
```

Confirm the only hunks are the additive ones described above. Any
non-additive line on a FROZEN row aborts the merge.

## DOD

- [ ] Envelope pair `audit.probe` / `audit.probe_ack` defined +
      tested
- [ ] `provenance_assertions` WAL table migrates cleanly + tested
- [ ] `audit_probe` kind in `desktop_commands.py` allowlist
- [ ] `audit_probe` HITL trigger reason in `hitl.py` enum
- [ ] `/api/sm-probe` GET + `/api/sm-probe/ack` POST endpoints
      live; SSE stream emits `audit.probe`
- [ ] Dashboard HITL panel renders audit-probe row variant with
      candidate-list radio buttons
- [ ] Cassette coverage extended same-cycle (per
      `feedback_cassette_must_cover_new_envelopes.md`)
- [ ] `--ppp-auto-probe` flag is opt-in (default OFF) in P1
- [ ] Self-monitor candidate-list filter live (P3 will harden it)
- [ ] All 4 test files added; full pytest suite green
- [ ] REQUIREMENTS.md FR-PPP-1..6 appended
- [ ] LOC budget ≤ 700 net add
- [ ] Sub-cycle close-out diff guard run; FROZEN seams additive only
- [ ] Cross-PR seam review (writer↔reader pairs) signed off
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `feat(ppp):`
- [ ] Alignment-eval `--ci-gate` exit 0 (PPP is advisory; must not
      regress alignment)
- [ ] Tier 1.5 smoke soak passes (per ADR-17 amendment from v2.0
      P2 trigger matrix; touching `governance.py` triggers Tier 1.5)

Report back when PR is open with: PR URL, diff stat, file list,
sample `audit.probe` envelope JSON, sample `provenance_assertions`
row, cassette fragment showing both envelopes round-tripped, and
the FROZEN-seam diff output (must be empty of non-additive hunks).
