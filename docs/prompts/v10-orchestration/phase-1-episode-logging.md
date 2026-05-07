You are implementing **Phase P1 — Episode logging (v10.0)** for the streamManager v10 RL companion track.

## Branch + base

- Base: `main` with v10 P0 (`docs/v10-rl-design.md` + `docs/v10-task-plan.md`) merged.
- PR target: `main`.
- Branch: `feat/v10-episode-logging` (or operator's choice).
- If P0 is not merged, ABORT (the formal design doc + phase prompts must be on `main` first).

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze is law. P1 must touch ONLY:

- `rl/__init__.py` — new package marker.
- `rl/episode_logger.py` — new module, single-writer process; SQLite WAL writer for `rl_episodes.db`.
- `rl/state_features.py` — new module; pure-function feature extractor over the gov-state dict (no imports from FROZEN modules' internals beyond public attributes).
- `rl/schema.sql` — new file; `episodes` table DDL.
- `tests/test_rl_episode_logger.py` — new test file.
- `tests/test_rl_state_features.py` — new test file.
- `docs/adr/ADR-5-latency-budget.md` — append a §"v10 logging overhead" subsection ONLY (additive doc edit).

NO edits to `governance.py`, `cli_governance.py`, `model_router.py`, `cli_pool.py`, `learn_mode.py`, `tools/soak_driver.py`, `tools/alignment_eval.py`, `dashboard/`, or any FROZEN symbol.

Pre-flight grep (run before any edit; if any symbol is missing, STOP — silent-revert trap):

```
grep -nE 'governance_decision|governance_envelope_missing_confidence|hitl_overrides|requires_alignment|RoutingDecision|classify_trigger_factor' src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/model_router.py
```

The episode logger reads ONLY:
- `governance_decision` bus envelopes (via subscribe).
- `hitl_overrides` table (read-only).
- `_last_phase_timings_ms` (read-only).

It writes ONLY:
- `rl_episodes.db` (dedicated file, separate from gov DB per seed D2).

## Task brief

Implement v10.0 episode logging. Pure data collection, zero policy effect. Per the design review (P2 — pessimistic offline RL preflight), the logger captures *propensity* (production policy is deterministic at v10.0 → propensity = 1.0) so that future off-policy correction (IPS / DR) is well-defined when exploration starts.

### Deliverables

1. **`rl/schema.sql`** — `episodes` table DDL:

   ```sql
   CREATE TABLE IF NOT EXISTS episodes (
       episode_id          INTEGER PRIMARY KEY AUTOINCREMENT,
       ts_utc              TEXT NOT NULL,
       session_id          TEXT NOT NULL,
       trace_id            TEXT NOT NULL,
       state_features_json TEXT NOT NULL,
       action_taken        REAL NOT NULL,
       action_propensity   REAL NOT NULL DEFAULT 1.0,
       verdict             TEXT NOT NULL,   -- ALLOW|SUGGEST|INTERVENE|BLOCK|AMBIGUOUS
       confidence          REAL NOT NULL,
       hitl_override       INTEGER,         -- nullable: 0/1/NULL
       latency_ms          REAL NOT NULL,
       fr_og_7_pass        INTEGER NOT NULL,-- 0/1
       budget_violation    INTEGER NOT NULL,-- 0/1
       source              TEXT NOT NULL,   -- soak|cassette|probe|golden|review|live
       cycle_tag           TEXT,            -- e.g. v2.0-shipgate-soak-20260520T...
       UNIQUE(session_id, trace_id)
   );
   CREATE INDEX IF NOT EXISTS idx_episodes_ts        ON episodes(ts_utc);
   CREATE INDEX IF NOT EXISTS idx_episodes_source    ON episodes(source);
   CREATE INDEX IF NOT EXISTS idx_episodes_cycle_tag ON episodes(cycle_tag);
   PRAGMA journal_mode=WAL;
   ```

2. **`rl/state_features.py`** — pure function `extract(state: Mapping) -> dict[str, float | int]` returning the v10 design-doc feature vector exactly:

   - `latency_ms_last5_p95: float`
   - `content_length: int`
   - `regex_destructive_match: int` (0/1)
   - `regex_alignment_match: int` (0/1)
   - `time_of_day_bucket: int` (0–23)
   - `session_history_action_share: list[float]` (length 5; rolling share over ALLOW/SUGGEST/INTERVENE/BLOCK/AMBIGUOUS)
   - `routing_band: int` (1–4)
   - `trigger_factor: int`
   - `learn_mode_bias_hint: float`

   Function is deterministic and pure — no I/O, no clock reads (caller supplies `now_utc`). Regex helpers re-use `_DESTRUCTIVE_PATTERNS` indirectly via a small adapter (do NOT import the symbol directly — re-declare equivalent patterns in `rl/state_features.py` and add a unit test that asserts pattern-set parity at least on the P1a probe corpus).

3. **`rl/episode_logger.py`** — dedicated writer. Subscribes to `governance_decision` bus envelopes; for each envelope:
   - resolve `state_features` via `rl.state_features.extract`,
   - look up matching `hitl_overrides` row (best-effort; NULL if absent),
   - read `_last_phase_timings_ms.get('cli_pool_send_ms')` for latency,
   - read `requires_alignment` outcome to determine `fr_og_7_pass` (1 if alignment-required AND verdict matches golden expectation, else fall back to 1 by default — only golden-replay episodes have known ground-truth),
   - insert into `rl_episodes.db` with `action_propensity=1.0` and `source='live'` for live envelopes; ingest from cassette / probe / golden runs uses explicit source tags via a dedicated CLI (`python -m rl.episode_logger ingest --source cassette --file ...`).

   Writer is a SINGLE process. Multiple SM instances writing concurrently must serialize via a file lock on `rl_episodes.db.lock`. WAL mode required.

4. **`rl/__init__.py`** — package marker; `__all__ = []` (do NOT re-export anything; consumers import explicit submodules).

5. **Tests** — `tests/test_rl_episode_logger.py` and `tests/test_rl_state_features.py`:
   - `test_extract_returns_design_doc_keys` — feature dict has exactly the v10 design-doc keys, no extras.
   - `test_extract_is_pure` — same input → same output across 100 calls.
   - `test_destructive_pattern_parity` — `regex_destructive_match` agrees with `_DESTRUCTIVE_PATTERNS` on the v1.9 P1a probe corpus (27 wrapped + 27 bare prompts).
   - `test_logger_inserts_one_row_per_envelope` — feed N synthetic `governance_decision` envelopes → N rows in DB.
   - `test_logger_unique_constraint` — duplicate `(session_id, trace_id)` raises `IntegrityError` (defends against bus-replay double-insert).
   - `test_logger_wal_mode` — `PRAGMA journal_mode` returns `wal` after init.
   - `test_logger_ingest_cassette_tag` — CLI ingest writes `source='cassette'` and `cycle_tag` matches the cassette filename UTC stamp.
   - `test_logger_no_self_monitor` — feeding an envelope with `session_id` matching SM's own session ID (configured via `BRIDGE_SM_SELF_SESSION_ID` env var) raises `ValueError("self-monitor refusal")` and is NOT inserted (memory: `feedback_no_self_monitor.md`).

6. **ADR-5 append** — new subsection §"v10 logging overhead": measured insert-per-decision overhead (target ≤ 5 ms p95; budget ≤ 10 ms p95). If overhead exceeds budget, the writer process is the wrong shape — STOP and re-design before merging.

### Logging-only invariant

P1 changes NO governance behaviour. After P1 merge:

- `cli_dispatch_ms` p95 must be unchanged ± 5 % vs the v2.0 baseline.
- All v1.7–v1.9 + v2.0 tests stay green.
- `governance_decision` envelope schema is byte-identical to v2.0.

If the post-P1 soak shows `cli_dispatch_ms` p95 regression > 5 %, the writer is on the hot path — fix BEFORE merging (offload to a queue + dedicated thread).

### LOC budget

Per ADR-18 Rule 3, P1 net add ≤ 500 lines of code (tests excluded but scrutinised). If draft exceeds, scope back schema or move CLI ingest to P2.

## DOD

- [ ] `rl/{__init__,schema.sql,state_features,episode_logger}.{py,sql}` created
- [ ] `tests/test_rl_{episode_logger,state_features}.py` created
- [ ] `docs/adr/ADR-5-latency-budget.md` §"v10 logging overhead" appended (overhead measurement attached)
- [ ] FROZEN-symbol pre-flight grep clean (no edits inside FROZEN files)
- [ ] Tier 3 soak post-P1 shows `cli_dispatch_ms` p95 within ± 5 % of v2.0 baseline
- [ ] All v1.7–v2.0 tests green
- [ ] LOC budget ≤ 500 net add (excl. tests + schema.sql)
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `rl:`

Report back when PR is open with: PR URL, diff stat, file list, post-P1 soak report path, logging-overhead measurement.
