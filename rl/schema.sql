-- v10 P1 — episode log schema for rl_episodes.db.
-- Dedicated DB per seed D2. WAL mode (single writer, multi-reader).

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
    fr_og_7_pass        INTEGER,         -- nullable: 1=pass, 0=fail, NULL=no ground-truth signal
    budget_violation    INTEGER NOT NULL,-- 0/1
    source              TEXT NOT NULL,   -- soak|cassette|probe|golden|review|live
    cycle_tag           TEXT,            -- e.g. v2.0-shipgate-soak-20260520T...
    UNIQUE(session_id, trace_id)
);

CREATE INDEX IF NOT EXISTS idx_episodes_ts        ON episodes(ts_utc);
CREATE INDEX IF NOT EXISTS idx_episodes_source    ON episodes(source);
CREATE INDEX IF NOT EXISTS idx_episodes_cycle_tag ON episodes(cycle_tag);

PRAGMA journal_mode=WAL;
