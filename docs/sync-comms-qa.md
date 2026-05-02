# Sync-comms / Brains-of-Operation Q&A

Tracking doc for the sync-comms scope conversation (2026-05-02).
Decisions here feed REQUIREMENTS.md and roadmap updates.

## Q1 — What does "sync" mean?

**Options considered:**
- (i) Gate-and-wait — caller blocks on SM verdict
- (ii) Active injection — SM emits unsolicited messages
- (iii) ACK protocol — two-phase commit
- (iv) Hybrid combos

**Decision:** Pure (i) gate-and-wait. No inject. No ACK.

**Rationale:** PreToolUse hook already implements (i). Locking the contract beats adding agency without demand signal. Inject deferred indefinitely.

**Storage follow-ups:**
- SQLite WAL bus already stores+classifies decisions (tables: messages, decisions, patterns L1-L4, sessions, agents, hitl_pending, hitl_overrides). No research needed.
- Markdown decision log = derived view via `GET /api/decisions/export?format=md`. SQLite stays source of truth.

See: `memory/project_sync_comms_q1_locked.md`

---

## Q2 — Desktop role shift?

**Options considered:**
- (a) No change — Desktop stays passive renderer
- (b) SM → Desktop one-way commands
- (c) Bidirectional control plane — full RPC

**Decision:** (c) bidirectional control plane.

**Open sub-question (raised 2026-05-02):**
Can SM UI have a frame that shows and mimics Desktop session command lines?
- I.e., live mirror of governed-session bash/tool calls inside SM dashboard
- Read-only tail of governed session's command stream

**Answer:** Yes. Feasible. Notes below.

### Mirror frame — feasibility

**Source data:** `messages` table already records `type='tool_call'` rows for the governed session. Bash invocations, file reads, edits — all there. SSE already streams them.

**Wire (read-side):**
```
governed session → PreToolUse hook → SM bus (messages table)
                                       ↓
                               SSE /events
                                       ↓
                       SM dashboard frame "Session Mirror"
                                       ↓
                         Renders command-line entries:
                         [HH:MM:SS] $ bash: git status
                         [HH:MM:SS] $ read: src/foo.py
                         [HH:MM:SS] $ edit: src/foo.py:42
```

**Constraints (SM-never-self-monitor rule):**
- SM cannot mirror its OWN session's JSONL.
- SM CAN mirror the governed (target) session's command stream — that is its job.
- Mirror frame filters strictly to `session_id != SM_OWN_SESSION_ID`.

**Mimic angle (bidirectional, per option c):**
Beyond read-only mirror, "mimic" implies SM dashboard can SEND commands back into governed session. This is the (c) bidirectional half.
- Outbound channel: SM dashboard → bus event `desktop_command` → governed session executes
- Examples: pause, foreground panel, surface a HITL prompt, request user attention
- Auth: governed-session-side hook trusts only signed bus events from SM (signing scheme TBD)

**Effort estimate:**
- Mirror frame (read-only): ~80 lines dashboard JS + ~20 lines SSE filter (~½ session)
- Bidirectional control plane (full c): ~3-4 sessions including auth, reconnect, schema, tests

**v1.0 scope (LOCKED 2026-05-02, REVISED same day):**
- Full option (c) lands in v1.0. NOT deferred. Design completed below.
- Desktop becomes active orchestrator surface in v1.0 ship.

**Rationale for in-v1.0 ship:** Defer creates wire-protocol churn risk between v1.0/v1.1. Designing now while context is loaded is cheaper than re-loading it later. Phase 6 session selector already implies multi-surface UI; finishing the orchestrator story closes the loop.

---

### Option (c) full design — v1.0

**Three deliverables in one phase:**

#### 1. Session Mirror frame (read side)

- New dashboard frame "Session Mirror" — live tail of governed session tool calls
- SSE source: `messages` table where `type IN ('tool_call','tool_result')`
- Filter: `session_id != SM_OWN_SESSION_ID` (no-self-monitor enforcement)
- Render: terminal-style log with timestamp + kind + args
```
[14:23:01.421] $ bash:  git status
[14:23:02.118] $ read:  src/foo.py
[14:23:04.302] $ edit:  src/foo.py:42
[14:23:05.991] $ bash:  pytest tests/test_foo.py
```
- Pause/clear/copy controls per Phase 6 event-log conventions

#### 2. Outbound `desktop_command` event (write side)

- New bus event type: `desktop_command`
- Payload schema:
```json
{
  "id": "uuid",
  "kind": "pause|foreground|flash|audible_cue|surface_hitl|request_attention",
  "target_session_id": "...",
  "args": {...},
  "signature": "hmac-sha256(...)",
  "issued_at": "iso8601",
  "ttl_s": 30
}
```
- Auth: HMAC-SHA256 over `id|kind|target_session_id|args|issued_at` using shared secret env `SM_DESKTOP_SECRET`
- Governed-session-side hook subscribes, validates signature, executes, emits `desktop_command_ack`

#### 3. Reply protocol + reconnect

- Ack event: `desktop_command_ack` with `{ command_id, status: 'ok'|'rejected'|'expired', error? }`
- SM dashboard tracks pending commands, surfaces ack status in UI
- Last-Event-ID resume (already shipped commit `6db5e78`) handles disconnect
- Unacked commands TTL=30s → marked `expired` automatically
- New WAL table `desktop_commands` (id, session_id, kind, args_json, sent_at, acked_at, status)

#### Wire shape

```
SM dashboard         SM bus          governed session
     │                 │                    │
     │ click "pause"   │                    │
     ├─POST /api/cmd──→│                    │
     │                 │ insert desktop_cmd │
     │                 ├──SSE──────────────→│ validate sig
     │                 │                    │ execute
     │                 │←─insert _ack──────┤
     │←──SSE update────│                    │
     │ shows acked     │                    │
```

#### REQUIREMENTS.md additions (v1.7)

- §4.10 Active orchestration
  - FR-DC-1 SM emits authenticated `desktop_command` events
  - FR-DC-2 Governed session validates HMAC signature; rejects on mismatch
  - FR-DC-3 Every command produces a `desktop_command_ack` within TTL
  - FR-DC-4 Session Mirror frame renders governed-session tool stream live
  - FR-DC-5 Mirror frame filters out SM's own session_id (no-self-monitor)

#### Effort

- Mirror frame: ~½ session
- desktop_command schema + HMAC + emit path: ~1 session
- Governed-side hook handler + ack: ~1 session
- Tests (sig validation, TTL, replay, ack roundtrip, mirror filter): ~½ session
- Docs/ADR: ~¼ session

**Total:** ~3¼ sessions for full option (c) in v1.0.

#### Open design questions — RESOLVED 2026-05-02

- **OQ1 (LOCKED):** (iii) **hybrid**. SM reads env `SM_DESKTOP_SECRET` first; if absent, auto-gens `secrets.token_urlsafe(32)` and persists to `.bridge/secret` (file mode 0600). Subsequent boots reuse file. Env always wins if set.
- **OQ2 (LOCKED):** (i) **one shared secret**. All SM instances + governed-session hooks read same `.bridge/secret`. Any SM signs, any hook validates. Single-user single-laptop scope. Per-instance keypairs deferred indefinitely.
- **OQ3 (LOCKED):** (iii) **lightweight validation only**. `desktop_command` events skip `engine.evaluate()` entirely — control plane bypass. Each emit undergoes schema check + HMAC signature check + kind-allowlist before bus insert. ADR records: "control plane bypasses governance; only inbound governed-session messages evaluated. Outbound commands undergo schema+sig+kind validation only."
- **OQ4 (LOCKED):** (i) **long-poll**. Governed-session hook calls `GET /api/commands/pending?session_id=X` every ~1s. SM responds with pending commands list (or empty). Hook executes, posts ack to `POST /api/commands/{id}/ack`. SSE upgrade deferred to v1.1.

**Status:** All Q2 design questions resolved. Ready for impl phase.

See: REQUIREMENTS.md §4 (Desktop role) — pending update

---

## Q3 — Multi-session capable?

**Options considered:**
- (a) Single-session
- (b) N concurrent, shared brain
- (c) N concurrent, isolated brains

**Decision (LOCKED 2026-05-02):** (c) isolated brains **+ opt-in cross-session learning** layer.

### Design

**Per-session isolation (default):**
- One engine instance per `session_id`. Each owns its own `DecisionGraph`, mode ladder, pattern counters.
- Session A's L4 promotion does NOT change session B's mode.
- Agent-mode-override semantics already shipped match this model (per-session override map).

**Cross-session learning (opt-in):**
- SQLite `patterns` table extended with `cross_session BOOL DEFAULT 0` column.
- Promotion criterion: pattern reaches L3 in any single session → engine flags `cross_session=1`.
- On new session engine init: hydrate cross-session-flagged patterns from SQLite at **L1 advisory level** (visibility), require local re-validation before promotion to L2+ in this session.
- Net effect: every new session inherits the **vocabulary** of known patterns but must independently validate behavior. No silent contamination.

**Shared state via SQLite (no in-memory sharing):**
- Engines never directly share mutable state across sessions.
- Cross-session signal flows through SQLite reads only.
- Periodic poll (e.g., every 60s) for new cross-session patterns added by sibling engines.

### REQUIREMENTS.md additions (v1.7)

- §3.x Multi-session model
  - NFR-MS-1 SM process governs N concurrent sessions, isolated brains
  - NFR-MS-2 Patterns reaching L3 in any session flagged cross-session
  - NFR-MS-3 New session engines hydrate cross-session patterns at L1 advisory
  - NFR-MS-4 No in-memory mutable state shared across session engines

### Effort

- Per-session engine instancing (refactor): ~1 session
- `patterns.cross_session` column + migration + flag-on-L3 logic: ~½ session
- New-session hydration path + L1-advisory injection: ~½ session
- Cross-session poll loop: ~¼ session
- Tests (isolation, hydration, no-contam): ~½ session

**Total:** ~2¾ sessions.

### Constraint check
- ✓ Q1 gate-and-wait: orthogonal, per-call logic unchanged.
- ✓ Q2 active orchestrator: each session has its own command/ack stream, target_session_id routes correctly.
- ✓ SM-never-self-monitor: SM's own session_id excluded from engine instancing.
- ✓ Phase 6 session selector: completes the UI promise.

### Open design questions — RESOLVED 2026-05-02

- **OQ5 (LOCKED):** (ii) **HITL-confirmed**. Pattern reaching L3 enters HITL queue with `trigger_reason=cross_session_flag`. Operator must approve before `cross_session=1` flag is set. Friction accepted to prevent silent leakage.
- **OQ6 (LOCKED):** (v) **manual demote UI + TTL gc**. Dashboard panel lists all `cross_session=1` patterns with explicit demote button (sets flag=0). Stale patterns also auto-gc'd via existing `last_seen` TTL. No auto-demote on per-decision HITL override (too implicit).
- **OQ7 (LOCKED):** (i) **no cap**. Engines spawn freely; ~25 MB × N. Revisit only if real-world OOM observed. No env knob, no warn banner in v1.0.
- **OQ8 (LOCKED):** (ii) **async bounded wait**. New-session engine returns immediately from init. Background thread hydrates `cross_session=1` patterns from SQLite within ~2s. Sync verdict path checks `hydrated?` flag — if not yet, decisions proceed without cross-session advisory (acceptable since L1 advisory only).

**Status:** All Q3 design questions resolved. Ready for impl phase.

---

## Update history

| date | change |
|---|---|
| 2026-05-02 | Doc created. Q1 locked. Q2 option (c) selected; mirror frame sub-Q raised + answered. Q3 pending. |
| 2026-05-02 | Q2 defer reversed — full option (c) ships in v1.0. Q3 locked: isolated brains + opt-in cross-session learning. |
| 2026-05-02 | OQ1–OQ8 all locked. v1.0 design freeze for sync-comms scope. |
