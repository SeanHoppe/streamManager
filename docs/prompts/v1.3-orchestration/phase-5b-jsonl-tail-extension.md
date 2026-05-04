You are implementing **Phase P5b — JSONL tail extension** from the streamManager v1.3 cycle (Learn Mode sub-cycle).

## Branch + base

- Base: `ship/v1.3-learn-mode` (NOT `main`).
- PR target: `ship/v1.3-learn-mode`.
- Branch: `feat/v1.3-jsonl-tail-learn-mode` off `ship/v1.3-learn-mode` (or operator's choice).
- If `ship/v1.3-learn-mode` does not exist, ABORT — P5a must ship first.

## Dependency

P5a (`docs/learn-mode-design.md`) MUST be merged on `ship/v1.3-learn-mode` first. Read that design doc before editing — it is the source of truth for ingest spec.

## ⚠️ CRITICAL: Do-not-touch guard

Protected symbols:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| (Phase 1 ingest) | `src/stream_manager/jsonl_tail.py` | existing emit paths — extend, do not replace |
| L (v1.1) | `src/stream_manager/message_bus.py` | `MessageBus` envelope schema (additive new `type` values only); `hitl_pending.matched_hash` |
| (cross-cutting) | SM's own JSONL emission path | DO NOT modify — would create self-monitor loop (memory `feedback_no_self_monitor.md`) |

Pre-flight grep:

```
grep -nE 'jsonl_tail|messages\.type|parentUuid|matched_hash' src/stream_manager/jsonl_tail.py src/stream_manager/message_bus.py
```

If `jsonl_tail.py` lacks the existing emit paths or `messages` table is missing `type` column, STOP and report.

## Task brief

Extend `src/stream_manager/jsonl_tail.py` to emit Desktop-orchestrator dialogue turns:

1. Emit `messages.type='desktop_prompt'` for `assistant` text turns from the JSONL stream.
2. Emit `messages.type='user_reply'` for `user` text turns.
3. Pair turns via `parentUuid` chain — emit a `pair_id` field linking each `user_reply` to its preceding `desktop_prompt`.
4. Exclude SM-originated turns: filter out any turn whose source matches the SM session's own JSONL emission signature. Per `feedback_no_self_monitor.md`, SM must never ingest its own HITL prompts (creates an evaluation feedback loop).

### Tests

- `tests/test_jsonl_tail_learn_mode.py`:
  - Synthesize a JSONL fixture with a paired `assistant`/`user` turn pair.
  - Add one SM-originated turn (matching the exclusion signature).
  - Assert: tailer emits `desktop_prompt` + `user_reply` with matching `pair_id`.
  - Assert: SM-originated turn is NOT emitted.

## DOD

- [ ] New message types emitted with paired `pair_id`
- [ ] SM HITL prompts excluded
- [ ] `tests/test_jsonl_tail_learn_mode.py` passes; existing JSONL-tail tests stay green
- [ ] `pytest -q` passes end-to-end
- [ ] No protected-symbol drift
- [ ] Single PR against `ship/v1.3-learn-mode`

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.3-learn-mode..HEAD --stat
```

Expected files:
- `src/stream_manager/jsonl_tail.py` (modified — new emit paths)
- `src/stream_manager/message_bus.py` (potentially modified — additive `type` values only)
- `tests/test_jsonl_tail_learn_mode.py` (new)
- `tests/fixtures/learn_mode_jsonl_sample.jsonl` (new — fixture)

If diff shows ANY change to SM's own JSONL emission path or to `MessageBus` non-additive surface, STOP and report.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail.
