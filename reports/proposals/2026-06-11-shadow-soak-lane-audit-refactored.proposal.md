# Shadow Soak Audit Lane with Polarity-Safe Filtering

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea SOAK-3; boldness STRETCH; refute verdict CONSTRAIN; effort L.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

The project MVP blocker (#112 -> #131 -> #124/#125) requires empirical shadow-soak validation of governance engine correctness. Current soak methodology is synthetic-prose-only (soak_driver.py injects at engine.evaluate step), which tests plumbing but not the live JsonlTailWorker -> bus -> governance -> decisions path. Live non-SM-session soaking exists (21366 decisions, 1252 sessions in gov.db) but is manual and unrepeatable: operators watch the dashboard and eyeball decisions without a dataflow for testing infrastructure to affirm "this session is canonical" and gate on agreement metrics. The proposal must convert this manual empirical validation into a first-class observability feature while strictly enforcing polarity: SM never reports governance state for its own sessions.

## Proposal

Introduce a Shadow Soak Audit Lane consisting of:

1. **Shadow Evaluation Worker** (`src/stream_manager/shadow_evaluator.py`, new module):
   - A background worker subscribed to the same message stream as the live governance engine.
   - On every incoming message (from any non-SM session, guaranteed by upstream filtering at JsonlTailWorker boot), instantiates a fresh copy of the DecisionGraph and replays the same `_evaluate_inner_core` logic as the live path.
   - Records verdicts atomically to `tmp/shadow_soak.db` (new WAL database with schema mirroring `decisions` table plus `shadow_decision_meta` for graph-state snapshots).
   - **Polarity gate (HARD)**: The worker reads `SM_OWN_SESSION_ID` env var at boot; any message with `session_id == SM_OWN_SESSION_ID` is discarded (not recorded to shadow_soak.db). This is a defensive write-time gate independent of upstream filtering.

2. **API Endpoints** (dashboard/server.py, new POST routes):
   - `POST /api/soak/shadow/status` -- Returns agreement metrics (last 50 decisions) with **HARD polarity filter**: `WHERE sessions.project_slug != 'streamManager' AND messages.session_id != SM_OWN_SESSION_ID` (env-cached at boot). Only includes rows where both live and shadow decisions exist for the same message_id.
   - `POST /api/soak/shadow/deltas` -- Per-decision delta rows (live_action, live_confidence, shadow_action, shadow_confidence, delta_reason) with pagination; applies same polarity filters.
   - Both endpoints JOIN decisions (live) + shadow_decisions + messages + sessions to ensure project_slug and session_id filtering happens at the SQL layer, not post-hoc in Python.

3. **Dashboard UI** (dashboard/ui-next/, EXPERIMENTAL spike):
   - `ShadowAuditCard.svelte` in Frame D (new component, docked). Shows: agreement % badge (green >95%, amber 85-95%, red <85%), decision count, timestamp of last shadow-run.
   - `ShadowDeltaDetail.svelte` -- decision-by-decision delta view, drillable from the card. Each row: `Decision #1234 [live=ALLOW(0.92) shadow=SUGGEST(0.68), delta=L2->L3 threshold crossed]`.
   - Settings toggle: 'Enable Shadow Soak Recording' (stores preference in `hitl_settings` table).

4. **Deterministic Replay Strategy** (defer exact replay fidelity to Phase 2):
   - Shadow worker captures the DecisionGraph state (pattern collection) at evaluation time and serializes it as a nullable `graph_snapshot` JSON blob in shadow_soak.db.
   - Alternatively, use lockstep replay: shadow worker runs immediately after live decision, both against the same in-memory graph object. This requires synchronous message handling (wrapping the bus publish in a lock).
   - For MVP, accept +/- 5% confidence delta as transient disagreement (artifact of async replay window), document it.

5. **Schema Additions** (tmp/shadow_soak.db):
   - `shadow_decisions` table: mirrors `decisions` schema + adds `graph_snapshot` (JSON, nullable), `evaluation_window_ms` (integer).
   - `shadow_audit_report` table: {decision_id, live_action, live_confidence, shadow_action, shadow_confidence, delta_reason, timestamp}.

6. **Cassette + Soak Coverage** (deferred, NOT blocking MVP):
   - A follow-up PR will extend `tools/cassette_record.py` to record shadow-path envelopes (new envelope kind) and `tools/soak_driver.py` to replay shadow-mode in Tier 3.
   - This PR does NOT add new bus envelope kinds; shadow recordings are internal to shadow_soak.db. MVP ships without cassette integration.

**Polarity Compliance (MUST):**
- Write-time: `shadow_evaluator.py` discards any message where `session_id == SM_OWN_SESSION_ID`.
- Read-time (API): Both `/api/soak/shadow/status` and `/api/soak/shadow/deltas` encode the filter at SQL JOINs: `WHERE sessions.project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS) AND messages.session_id != SM_OWN_SESSION_ID`.
- Rationale: upstream JsonlTailWorker filtering + session_watcher checks prevent SM-self sessions from reaching the bus. But the shadow database may accumulate rows if a session later transitions to self-monitor status (session watcher probe flow). The API filter is the defensive last-mile gate.


## Operator value

Operators gain a continuous, repeatable audit of governance engine correctness without manual observation. (a) Agreement % metric surfaces immediate post-code-change drift (was 98% live-vs-shadow on commit A; dropped to 67% on commit B -> investigate). (b) Per-decision delta rows become a regression-test corpus: file an issue with a delta row attached; reviewers can deterministically replay that exact input. (c) The shadow lane runs in a background worker and does not disrupt live sessions, allowing empirical soak to run in production on real operator/agent traffic (satisfies #r1 requirement). (d) Latency metrics: shadow evaluation happens async, so it does not block live governance; drift metric is low-cost observability, not a decision blocker.

## Surfaces touched / added

- src/stream_manager/shadow_evaluator.py (new module: background worker, tails messages, evaluates shadow DecisionGraph, records to shadow_soak.db, enforces SM_OWN_SESSION_ID filter at write-time)
- dashboard/server.py: POST /api/soak/shadow/status (returns agreement %, applies polarity SQL filter)
- dashboard/server.py: POST /api/soak/shadow/deltas (returns per-decision deltas, applies polarity SQL filter)
- dashboard/ui-next/src/lib/ShadowAuditCard.svelte (new card in Frame D: agreement badge + timestamp)
- dashboard/ui-next/src/lib/ShadowDeltaDetail.svelte (decision-by-decision delta detail view)
- tmp/shadow_soak.db (new WAL database: shadow_decisions + shadow_audit_report tables, polarity-filtered in reads via API)
- src/stream_manager/message_bus.py (extend: optional shadow_evaluator subscription when shadow mode enabled, no schema change to existing bus envelopes)

## Feasibility

HARD (but solvable, not infeasible). Reasons: (1) Shadow worker logic is straightforward -- same DecisionGraph import, same graph.match() + confidence-threshold logic as live path. (2) Message-stream subscription pattern is proven (HITL queue, Learn Mode, JsonlTailWorker all use it). (3) New shadow_soak.db schema is a WAL mirror, doable. (4) **The hard part**: deterministic replay requires either (a) freezing the DecisionGraph state at evaluation time and passing snapshots to the shadow lane (requires schema change to carry graph_snapshot JSON), or (b) synchronous lockstep evaluation (requires wrapping message handling in a lock, impacts latency budget). Option (a) is preferred for MVP (async, no latency hit); MVP accepts +/- 5% confidence delta as transient disagreement and documents the replay window. Option (b) is Post-MVP for "perfect" determinism. (5) **Cassette integration** (new bus envelope kind for shadow-mode playback) is deferred to follow-up PR; not blocking MVP, because shadow recordings are internal to shadow_soak.db, not a new bus envelope type exposed to external consumers.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS. The shadow evaluator reads from the same SSE message stream and decision flow that non-SM sessions already expose. It introduces no new certPortal vocabulary or coupling. The `project_slug` filter and SM_OWN_SESSION_ID gate are inherited from upstream (session_watcher + jsonl_tail already block SM-self sessions before reaching the bus) and reinforced at the API layer.
- **Polarity (G2):** CONSTRAINED to PASS (was FAIL in original idea). Write-time: shadow_evaluator.py reads SM_OWN_SESSION_ID env var at boot and discards any message where session_id == SM_OWN_SESSION_ID (defensive gate independent of upstream filtering). Read-time: both `/api/soak/shadow/status` and `/api/soak/shadow/deltas` encode hard SQL filters at JOIN points: `WHERE sessions.project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS) AND messages.session_id != SM_OWN_SESSION_ID`. These filters ensure no operator ever sees agreement metrics or decision deltas for SM's own sessions, even if a session later transitions to self-monitor status (session-watcher probe). The proposal does NOT add new bus envelope kinds (shadow recordings stay internal to shadow_soak.db), so no new vector for polarity leakage.
- **ADR-18 MUST floor:** PASS. The proposal targets the EXPERIMENTAL ui-next spike + SM backend. It does NOT modify FROZEN surfaces (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py). All new surfaces are additive: shadow_evaluator.py (new), /api/soak/* endpoints (new), ShadowAuditCard.svelte + ShadowDeltaDetail.svelte (new components in EXPERIMENTAL ui-next), shadow_soak.db schema (new database). message_bus.py is extended (not modified) to emit shadow subscriptions; this is an EVOLVING surface per ADR-18. The nine MUST invariants (M1-M9 from ADR-20) are respected: the shadow audit is a monitor-first, informational panel (no auto-foreground), paired label+color badges, no domain-specific vocabulary hardcoded.
- **Frozen-surface note:** No FROZEN surfaces modified. No ADR amendment required. message_bus.py is EVOLVING (per ADR-18), and extending it with an optional subscriber does not cross the freeze boundary.
- **New-envelope note:** The proposal does NOT introduce a new bus envelope kind. Shadow recordings are internal to shadow_soak.db; they do not flow through the main message_bus SSE stream. A future PR may add a new 'shadow_audit_cassette' envelope kind for Tier 3 soak driver replay (cassette_record.py + soak_driver.py coverage), but this MVP ships without cassette integration. That follow-up PR WILL require cassette_record.py + soak_driver.py coverage as a same-PR gate.

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\INTENT.md:97-121 (current cycle posture, MVP blocker #112->#131->#124/#125)
- C:\Users\SeanHoppe\vs\streamManager\reports\soak-for-non-sm-sessions.md:92-121 (live tail path, polarity definition, #r1 requirement)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\governance.py:1616-1680 (SM_OWN_SESSION_ID gate, self-monitor refusal)
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\message_bus.py:52-58 (sessions table with project_slug, schema baseline)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:720-755 (existing API session filtering pattern)
- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-20-ui-redesign-experimental-spike.md:35-77 (EXPERIMENTAL surface classification, MUST-floor M1-M9, ADR-18 Rule 1)
