You are implementing **Phase P3 — Learn Mode JSONL source expansion** from the streamManager v1.9 cycle.

## Branch + base

- Base: `main` with v1.9 P0 (`docs/v1.9-cycle-frame`) merged.
- PR target: `main`.
- Branch: `feat/v1.9-learn-mode-sources` (or operator's choice).
- P3 is independent of P1 and P2 — it may land before, after, or in parallel with them. P0 must be merged first.

## ⚠️ CRITICAL: Do-not-touch guard

The full v1.1–v1.8 protected-symbol set in `docs/v1.9-task-plan.md` §"CRITICAL: do-not-touch list" applies. P3 must touch ONLY:

- `src/stream_manager/learn_mode.py` — `learn_sources` config + source ingest + label tagging; self-monitor guard
- `docs/learn-mode-design.md` (or `docs/smartai.md`, whichever is the primary Learn Mode design doc — check by reading HEAD) — update to document `learn_sources` config field
- `tests/test_learn_mode_sources.py` (NEW file)
- Schema/migration: `hitl_overrides` WAL table may need a new nullable `source_label` column (additive only — no column renamed, no existing data affected)

NO edits to `governance.py`, `cli_governance.py`, `model_router.py`, `session_watcher.py`, `cli_pool.py`, `tools/soak_driver.py`, or any v1.3 protected symbol.

The v1.3 protected advisory bias surface must remain fully intact:

```
grep -nE '_consult_learn_mode_bias|_emit_learn_mode_bias_applied|bias_consult|bias_hint' src/stream_manager/learn_mode.py src/stream_manager/governance.py
```

All four symbols must appear. If any is missing, STOP — silent-revert trap.

## Task brief

Learn Mode (`v1.3`) ingests only the SM Desktop session JSONL. certPortal oversight agents (Dave/Jen/Jason/Matt/Oliver/Michael) produce rich PASS/FAIL reasoning, retry patterns, and escalation triggers across hundreds of turns per day. This is exactly the signal SM's categoriser should be trained on, but the ingest pipeline never sees it. P3 makes the ingest source list configurable.

The self-monitor guard is the critical safety invariant: if any configured source resolves to SM's own JSONL output, it must be rejected — no eval feedback loops. This rule comes from `feedback_no_self_monitor.md` and applies even if the operator explicitly configures such a path.

### Deliverables

1. **`src/stream_manager/learn_mode.py`** — add `learn_sources` config and multi-source ingest:

   - **Config structure:**
     ```python
     # One entry per external JSONL source to ingest.
     # path_glob: resolved with pathlib.Path.glob; label: attribution tag.
     # Default: [] (off; opt-in per source).
     LEARN_SOURCES_ENV: str = "BRIDGE_LEARN_SOURCES"  # JSON-encoded list
     ```
     Runtime config is a list of `{"path_glob": str, "label": str}` dicts. Loaded from `BRIDGE_LEARN_SOURCES` env var (JSON-encoded) or from a config file key if a config loader already exists. Default: empty list.

   - **Source ingest:** for each configured source, tail-watch the glob for new JSONL entries (same mechanism as the existing Desktop session tail-watcher). Tag each ingested turn with `source_label` before passing to the categoriser. The categoriser and bias advisory surface are unchanged — label is metadata on the turn, not a routing modifier.

   - **Self-monitor guard:** before ingesting any file path from a configured source, check:
     - Does the resolved path overlap with `~/.claude/sessions/<SM-session-id>.jsonl`? If yes → REJECT with a `WARNING`-level log (`"learn_sources: rejecting path {path} — matches SM-internal session JSONL; eval feedback loop prevention"`). Do NOT ingest, do NOT raise an exception.
     - Does the resolved path contain `stream_manager` in any path segment? If yes → same rejection.
     - Guard applies at each glob expansion, not just at config load time (files may appear later).

   - **`hitl_overrides` WAL table** — add nullable `source_label TEXT` column if it does not already exist (additive migration, idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). Populated from the tagged turn's `source_label` on categorised entries. Null for Desktop session turns (no change to existing rows).

   - **Isolation invariant:** turns from source A and source B must not influence each other's categorisation (each is a separate JSONL tail; they are queued independently). The categoriser processes one turn at a time regardless of source; label tagging is metadata-only.

2. **Documentation** — update the primary Learn Mode design doc (find it with `find docs -name "learn-mode-design.md" -o -name "smartai.md" | head -5`). Add a `## learn_sources config` section documenting: format, env var, self-monitor guard behaviour, label propagation to `hitl_overrides`. Append-only to the existing doc.

3. **Tests** (`tests/test_learn_mode_sources.py` NEW):
   - `test_empty_sources_default_unchanged` — no `learn_sources` configured → existing Desktop session ingest path runs as before; no new ingest threads started.
   - `test_source_turns_tagged_with_label` — one source configured with label `"certportal-oversight"` → ingested turns have `source_label == "certportal-oversight"` before categorisation; Desktop session turns remain unlabelled (null).
   - `test_self_monitor_guard_sm_session_path` — source glob resolves to SM's own JSONL session file → rejected with WARNING; no turns ingested from that path.
   - `test_self_monitor_guard_stream_manager_path_segment` — source path contains `stream_manager` segment → rejected with WARNING.
   - `test_self_monitor_guard_does_not_raise` — guard rejection does NOT raise an exception; other sources in the same config are unaffected.
   - `test_two_sources_isolated` — two sources (labels `"source-a"`, `"source-b"`) → turns from each are tagged independently; no cross-contamination.
   - `test_hitl_overrides_has_source_label_column` — after DB init, `hitl_overrides` table has `source_label` column (nullable); existing rows unaffected.
   - `test_source_label_null_for_desktop_session` — Desktop session turns (no source config) → `source_label` is null in `hitl_overrides`.

   Existing Learn Mode fast-tier tests MUST stay green: `tests/test_learn_mode.py` (or equivalent). Check what Learn Mode tests exist with `find tests -name "*learn*" -o -name "*categorize*"` before writing.

4. **No new bus envelopes** — P3 adds no new bus envelope types. Label tagging is internal to the ingest pipeline. Verify:
   ```
   grep -rn '"learn_source' src/stream_manager/learn_mode.py
   ```
   Any new envelope type starting with `learn_source` would be a scope violation.

### Advisory bias surface invariant

The Learn Mode advisory bias surface (`_consult_learn_mode_bias`, bias advisory read from `hitl_overrides` WAL) is untouched. P3 only extends the write side (ingest + label tagging). The advisory output seen by `governance._evaluate_inner_core` is unchanged in format and semantics. Verify by confirming no change to `_consult_learn_mode_bias` or its callers:

```
git --no-pager diff origin/main..HEAD -- src/stream_manager/governance.py
```

Expected: empty.

### Memory feedback applied

- `feedback_no_self_monitor.md` — self-monitor guard implemented and tested; guard covers both exact-path and path-segment matches; applies at glob expansion time, not just config load
- `feedback_cassette_must_cover_new_envelopes.md` — verified P3 introduces no new bus envelopes; no cassette changes required
- `feedback_subagent_stale_mental_model.md` — pre-flight grep before any edit

## DOD

- [ ] `src/stream_manager/learn_mode.py` has `LEARN_SOURCES_ENV`, source config loading, per-source tail-watcher, label tagging, self-monitor guard
- [ ] `hitl_overrides` WAL table has nullable `source_label` column; migration is idempotent
- [ ] Default empty `learn_sources` → existing Desktop session ingest path unchanged
- [ ] Self-monitor guard rejects SM-internal paths with WARNING; no exception; no turns ingested
- [ ] Primary Learn Mode design doc updated with `## learn_sources config` section
- [ ] 8 new test scenarios in `tests/test_learn_mode_sources.py`; all pass
- [ ] Existing `tests/test_learn_mode.py` (or equivalent) tests all pass
- [ ] `pytest tests/ -m "not slow and not alignment_eval" -q` → all pass
- [ ] `git --no-pager diff origin/main..HEAD -- src/stream_manager/governance.py` → empty (advisory bias surface untouched)
- [ ] No new bus envelope types
- [ ] `docs/use-cases/uc-01-external-session-monitoring.md` AC-2 satisfied (document in PR description which test verifies it)
- [ ] Single PR against `main`

## Mint-new-phase rule

After P3 implementation and before ticking DOD:
- If any existing `test_learn_mode.py` scenario regresses: STOP — P3 modified the existing ingest path; audit `learn_mode.py` diffs.
- If self-monitor guard raises an exception on rejection (instead of WARNING + continue): STOP — guard must not interrupt the ingest loop for other sources.
- If `hitl_overrides` migration breaks existing rows: STOP — `ALTER TABLE ... ADD COLUMN` must be idempotent; verify on a fresh DB and on an existing DB.
- If neither: P3 is unblocked.

Report back when PR is open with: PR URL, diff stat, test count (new + total), AC-2 verification note, self-monitor guard behaviour summary.
