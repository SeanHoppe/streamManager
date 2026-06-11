# Proposal: clarify CLAUDE.md L35-42 to document the dual-key write-time / read-time split

- **Finding:** F-POLARITY-Q (cavecrew review, 2026-06-11) — the read-side polarity filter in `rl/ope.py` (`load_episodes_from_db`) and `rl/corpus_augment.py` (`_load_real_from_db`) applies **only** the `project_slug` half of CLAUDE.md L42's dual self-exclusion key. Severity ❓ (confirm-intentional).
- **Disposition:** PROPOSAL (governance-doc change). The code is correct and a clarifying in-code comment has been added; this proposal recommends a matching CLAUDE.md clarification so doc and implementation agree. CLAUDE.md is a governance doc, so the wording change is surfaced here rather than edited unilaterally inside a code-fix partition.

## Problem

CLAUDE.md "Session-source exception rule (polarity-flip)" states the inclusion predicate as a **dual key, both halves at the SQL WHERE**:

```
INCLUDE iff session.project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)
        AND session_id != BRIDGE_SM_SELF_SESSION_ID
...
Filter at SQL WHERE, not post-hoc Python.
```

The implementation's read-side SQL WHERE carries only the `project_slug` term:

```sql
WHERE source IN (...) AND (project_slug IS NULL OR project_slug NOT IN (?, ...))
```

There is no `session_id != BRIDGE_SM_SELF_SESSION_ID` term at read time. Read literally, the code diverges from the documented rule — which is exactly what the ❓ finding flagged, and what an adversarial reviewer escalated to a REFUTE on the grounds that "CLAUDE.md L42 mandates *Filter at SQL WHERE* for the dual key."

## Root cause

The dual-key **invariant** ("no SM-self session contributes a row to the corpus") is upheld, but the **mechanism is split across two times**, not applied twice at read time:

- **`session_id` half — enforced at WRITE time.** `rl/episode_logger.py` raises `SelfMonitorRefusal` when `session_id == BRIDGE_SM_SELF_SESSION_ID`, so an SM-self session never writes an episode row in the first place. (Verified: `episode_logger` checks `session_id` against the self-session env var and raises before insert.)
- **`project_slug` half — enforced at READ time.** The read-side WHERE default-excludes the SM slug set, so any historical row carrying an SM `project_slug` is filtered on the way out.

Applying the `session_id` half at **read** time would be inert-to-harmful: `BRIDGE_SM_SELF_SESSION_ID` names the **current** session, which has no meaningful relationship to the `session_id` stored on a **historical** episode row. Filtering historical rows by the current session id excludes nothing useful (no historical row carries the current session id) and risks confusing future readers into thinking read-time session filtering is load-bearing. So `project_slug` is the only **durable** read-side key — precisely the conclusion the finding's author reached.

## Recommended change (CLAUDE.md, governance doc)

Amend the "Session-source exception rule (polarity-flip)" section so the doc states the invariant **and its split enforcement**, e.g. append after the code block:

> **Enforcement is split by time, not duplicated at read time.** The `session_id != BRIDGE_SM_SELF_SESSION_ID` half is enforced at **write** time (`episode_logger` raises `SelfMonitorRefusal`); `BRIDGE_SM_SELF_SESSION_ID` names the *current* session and is meaningless against historical rows, so it is **not** added to the read-side WHERE. The `project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)` half is the durable read-side key and is the term that appears in the read-side SQL WHERE. "Filter at SQL WHERE" governs the `project_slug` half; the `session_id` half is a write-time gate.

This makes the doc and the implementation agree, and pre-empts the next reviewer who reads L42 literally.

## In-code change already applied (this cycle)

The read-side comment in both `rl/ope.py` and `rl/corpus_augment.py` was updated to frame the divergence as compliance-via-split:

```
# CLAUDE.md L42's dual-key self-exclusion is upheld via a write-time /
# read-time SPLIT, not by dropping half the rule: the
# session_id != BRIDGE_SM_SELF_SESSION_ID half is enforced at WRITE time
# (episode_logger raises SelfMonitorRefusal) because that env var names
# the *current* session and is meaningless against historical rows; only
# the project_slug half is durable at read time, so the read-side SQL
# WHERE carries it alone.
```

## Evidence

- `rl/ope.py` `load_episodes_from_db` — read-side SQL WHERE: `project_slug`-only.
- `rl/corpus_augment.py` `_load_real_from_db` — read-side SQL WHERE: `project_slug`-only.
- `rl/episode_logger.py` — `SelfMonitorRefusal` raised on `session_id == BRIDGE_SM_SELF_SESSION_ID` (write-time session gate), verified by the Partition-B invariant reviewer.
- CLAUDE.md "Session-source exception rule (polarity-flip)" — the dual-key text + "Filter at SQL WHERE".
- `feedback_no_self_monitor.md` §"Polarity flip" (cross-ref in CLAUDE.md).
